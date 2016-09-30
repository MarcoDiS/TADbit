from pytadbit.utils.file_handling         import mkdir, magic_open
from itertools                            import combinations
from os                                   import path, system
from sys                                  import stdout
from collections import OrderedDict

def eq_reads(rd1, rd2):
    """
    Compare reads accounting for multicontacts
    """
    return rd1.split('~', 1)[0] == rd2.split('~', 1)[0]

def gt_reads(rd1, rd2):
    """
    Compare reads accounting for multicontacts
    """
    return rd1.split('~', 1)[0] > rd2.split('~', 1)[0]

def merge_2d_beds(path1, path2, outpath):
    """
    Merge two result files (file resulting from get_intersection or from
       the filtering) into one.

    :param path1: path to first file
    :param path2: path to first file

    :returns: number of reads processed
    """
    fh1 = open(path1)
    fh2 = open(path2)
    # parse header
    chromosomes = OrderedDict()
    parsed = 0
    for line in fh1:
        if not line.startswith('#'):
            break
        parsed += len(line)
        if not line.startswith('# CRM'):
            continue
        _, _, crm, val = line.split()
        chromosomes[crm] = val
    fh1.seek(parsed)
    # check other headers
    parsed = 0
    for line in fh2:
        if not line.startswith('#'):
            break
        parsed += len(line)
        if not line.startswith('# CRM'):
            continue
        _, _, crm, val = line.split()
        if chromosomes[crm] != val:
            raise Exception('ERROR: files are the result of mapping on '
                            'different reference genomes')
    fh2.seek(parsed)
    # comparison function
    greater = lambda x, y: x.split('\t', 1)[0].split('~')[0] > y.split('\t', 1)[0].split('~')[0]
    # write headers
    out = open(outpath, 'w')
    for crm in chromosomes:
        out.write('# CRM %s\t%s\n' % (crm, chromosomes[crm]))
    # merge sort the two files
    read1 = fh1.next()
    read2 = fh2.next()
    nreads = 0
    while True:
        if greater(read2, read1):
            out.write(read1)
            nreads += 1
            try:
                read1 = fh1.next()
            except StopIteration:
                out.write(read2)
                nreads += 1
                break
        else:
            out.write(read2)
            nreads += 1
            try:
                read2 = fh2.next()
            except StopIteration:
                out.write(read1)
                nreads += 1
                break
    for read in fh1:
        out.write(read)
        nreads += 1
    for read in fh2:
        out.write(read)
        nreads += 1
    fh1.close()
    fh2.close()
    out.close()
    return nreads
    
def get_intersection(fname1, fname2, out_path, verbose=False):
    """
    Merges the two files corresponding to each reads sides. Reads found in both
       files are merged and written in an output file.

    Dealing with multiple contacts:
       - a pairwise contact is created for each possible combnation of the
         multicontacts. The name of the read is extended by '# 1/3' in case
         the reported pairwise contact corresponds to the first of 3 possibles
       - it may happen that different contacts are mapped on a single RE fragment
         (if each are on different end), in which case:
          - if no other fragment from this read are mapped than, both are kept
          - otherwise, they are merged into one longer (as if they were mapped
            in the positive strand)

    :param fname1: path to a tab separated file generated by the function
       :func:`pytadbit.parsers.sam_parser.parse_sam`
    :param fname2: path to a tab separated file generated by the function
       :func:`pytadbit.parsers.sam_parser.parse_sam`
    :param out_path: path to an outfile. It will written in a similar format as
       the inputs

    :returns: final number of pair of interacting fragments, and a dictionary with
       the number of multiple contacts (keys of the dictionary being the number of
       fragment cought together, can be 3, 4, 5..)
    """
    
    # Get the headers of the two files 
    reads1 = magic_open(fname1)
    line1 = reads1.next()
    header1 = ''
    while line1.startswith('#'):
        if line1.startswith('# CRM'):
            header1 += line1
        line1 = reads1.next()
    read1 = line1.split('\t', 1)[0]

    reads2 = magic_open(fname2)
    line2 = reads2.next()
    header2 = ''
    while line2.startswith('#'):
        if line2.startswith('# CRM'):
            header2 += line2
        line2 = reads2.next()
    read2 = line2.split('\t', 1)[0]
    if header1 != header2:
        raise Exception('seems to be mapped onover different chromosomes\n')

    # prepare to write read pairs into different files
    # depending on genomic position
    nchunks = 1024
    global CHROM_START
    CHROM_START = {}
    cum_pos = 0
    for line in header1.split('\n'):
        if line.startswith('# CRM'):
            _, _, crm, pos = line.split()
            CHROM_START[crm] = cum_pos
            cum_pos += int(pos)
    lchunk = cum_pos / nchunks
    buf = dict([(i, []) for i in xrange(nchunks + 1)])
    # prepare temporary directories
    tmp_dir = out_path + '_tmp_files'
    mkdir(tmp_dir)
    for i in xrange(nchunks / int(nchunks**0.5) + 1):
        mkdir(path.join(tmp_dir, 'rep_%03d' % i))

    # iterate over reads in each of the two input files
    # and store them into a dictionary and then into temporary files
    # dicitonary ois emptied each 1 milion entries
    if verbose:
        print ('Getting intersection of reads 1 and reads 2:')
    count = 0
    count_dots = -1
    multiples = {}
    try:
        while True:
            if verbose:
                if not count_dots % 10:
                    stdout.write(' ')
                if not count_dots % 50:
                    stdout.write('%s\n  ' % (
                        ('  %4d milion reads' % (count_dots)) if
                        count_dots else ''))
                if count_dots >= 0:
                    stdout.write('.')
                    stdout.flush()
                count_dots += 1
            for _ in xrange(1000000): # iterate 1 million times, write to files
                # same read id in both lianes, we store put the more upstream
                # before and store them
                if eq_reads(read1, read2):
                    count += 1
                    _process_lines(line1, line2, buf, multiples, lchunk)
                    line1 = reads1.next()
                    read1 = line1.split('\t', 1)[0]
                    line2 = reads2.next()
                    read2 = line2.split('\t', 1)[0]
                # if first element of line1 is greater than the one of line2:
                elif gt_reads(read1, read2):
                    line2 = reads2.next()
                    read2 = line2.split('\t', 1)[0]
                else:
                    line1 = reads1.next()
                    read1 = line1.split('\t', 1)[0]
            write_to_files(buf, tmp_dir, nchunks)
    except StopIteration:
        reads1.close()
        reads2.close()
    write_to_files(buf, tmp_dir, nchunks)
    if verbose:
        print '\nFound %d pair of reads mapping uniquely' % count

    # sort each tmp file according to first element (idx) and write them
    # to output file (without the idx)
    # sort also according to read 2 (to filter duplicates)
    #      and also according to strand
    if verbose:
        print 'Sorting each temporary file by genomic coordinate'

    out = open(out_path, 'w')
    out.write(header1)
    for b in buf:
        if verbose:
            stdout.write('\r    %4d/%d sorted files' % (b + 1, len(buf)))
            stdout.flush()
        out.write(''.join(['\t'.join(l[1:]) for l in sorted(
            [l.split('\t') for l in open(
                path.join(tmp_dir, 'rep_%03d' % (b / int(nchunks**0.5)),
                          'tmp_%05d.tsv' % b))],
            key=lambda x: (x[0], x[8], x[9], x[6]))]))
    out.close()

    if verbose:
        print '\nRemoving temporary files...'
    system('rm -rf ' + tmp_dir)
    return count, multiples

def _loc_reads(r1, r2):
    """
    Put upstream read before, get position in buf
    """
    pos1 = CHROM_START[r1[1]] + int(r1[2])
    pos2 = CHROM_START[r2[1]] + int(r2[2])
    if pos1 > pos2:
        r1, r2 = r2, r1
        pos1, pos2 = pos2, pos1
    return r1, r2, pos1

def write_to_files(buf, tmp_dir, nchunks):
    for b in buf:
        out = open(path.join(tmp_dir, 'rep_%03d' % (b / int(nchunks**0.5)),
                             'tmp_%05d.tsv' % b), 'a')
        out.write('\n'.join(buf[b]))
        if buf[b]: # case the file was empty
            out.write('\n')
        out.close()
        del(buf[b][:])

def _process_lines(line1, line2, buf, multiples, lchunk):
    # case we have potential multicontacts
    if '|||' in line1 or '|||' in line2:
        elts = {}
        for read in line1.split('|||'):
            nam, crm, pos, strd, nts, beg, end = read.strip().split('\t')
            elts.setdefault((crm, beg, end), []).append(
                (nam, crm, pos, strd, nts, beg, end))
        for read in line2.split('|||'):
            nam, crm, pos, strd, nts, beg, end = read.strip().split('\t')
            elts.setdefault((crm, beg, end), []).append(
                (nam, crm, pos, strd, nts, beg, end))
        # write contacts by pairs
        # loop over RE fragments
        for elt in elts:
            # case we have 2 read-frags inside current fragment
            if len(elts[elt]) == 1:
                elts[elt] = elts[elt][0]
            # case all fragments felt into a single RE frag
            # we take only first and last
            elif len(elts) == 1:
                elts[elt] = sorted(
                    elts[elt], key=lambda x: int(x[2]))[::len(elts[elt])-1]
                elts1 = {elt: elts[elt][0]}
                elts2 = {elt: elts[elt][1]}
            # case we have several read-frag in this RE fragment
            else:
                # take first and last
                map1, map2 = sorted(
                    elts[elt], key=lambda x: int(x[2]))[::len(elts[elt])-1]
                strand = map1[3]
                # if the 2 strands are different keep the longest fragment
                if strand != map2[3]:
                    map1 = tuple(max(elts[elt], key=lambda x: int(x[4])))
                    elts[elt] = map1
                    continue
                elts[elt] = map1
                # sum up read-frags in the RE fragment  by putting
                # them on the same strand
                # use the strand of the first fragment as reference
                if strand == '1':
                    beg = int(map1[2])
                    nts = int(map2[2]) + int(map2[4]) - beg
                else:
                    beg = int(map2[2])
                    nts = beg - (int(map1[2]) - (int(map1[4])))
                elts[elt] = tuple(list(map1[:2]) + [str(beg), strand, str(nts)]
                                  + list(map1[5:]))
        contacts = len(elts) - 1
        if contacts > 1:
            multiples.setdefault(contacts, 0)
            multiples[contacts] += 1
            prod_cont = contacts * (contacts + 1) / 2
            for i, (r1, r2) in enumerate(combinations(elts.values(), 2)):
                r1, r2, idx = _loc_reads(r1, r2)
                buf[idx / lchunk].append('%d\t%s#%d/%d\t%s\t%s' % (
                    idx, r1[0], i + 1, prod_cont, '\t'.join(r1[1:]),
                    '\t'.join(r2[1:])))
        elif contacts == 1:
            r1, r2, idx = _loc_reads(elts.values()[0], elts.values()[1])
            buf[idx / lchunk].append('%d\t%s\t%s' % (idx, '\t'.join(r1), '\t'.join(r2[1:])))
        else:
            r1, r2, idx = _loc_reads(elts1.values()[0], elts2.values()[0])
            buf[idx / lchunk].append('%d\t%s\t%s' % (idx, '\t'.join(r1), '\t'.join(r2[1:])))
    else:
        r1, r2, idx = _loc_reads(line1.strip().split('\t'), line2.strip().split('\t'))
        buf[idx / lchunk].append('%d\t%s\t%s' % (idx, '\t'.join(r1), '\t'.join(r2[1:])))

