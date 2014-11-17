"""
17 nov. 2014


"""
from bisect import bisect
from pysam import Samfile

def parse_sam(f_names1, f_names2, frags, out_file1, out_file2, verbose=False):
    """
    Parse sam/bam file using pysam tools.

    Keep a summary of the results into 2 tab-separated files that will contain 6
       columns: read ID, Chromosome, position, strand (either 0 or 1), mapped
       sequence lebgth, position of the closest upstream RE site, position of
       the closest downstream RE site

    :param f_names1: a list of path to sam/bam files corresponding to the
       mapping of read1, can also  be just one file
    :param f_names1: a list of path to sam/bam files corresponding to the
       mapping of read2, can also  be just one file
    :param frags: a dictionary generated by :func:`pyatdbit.mapping.restriction_enzymes.map_re_sites`.

    """
    frag_chunk = frags['_chunk_size']
    frag_count = frags['_frag_count']

    fnames = f_names1, f_names2
    for read in range(2):
        if verbose:
            print 'Loading read' + str(read + 1)
        reads    = []
        for fnam in fnames[read]:
            if verbose:
                print 'loading file:', fnam
            try:
                fhandler = Samfile(fnam)
            except IOError:
                continue
            i = 0
            crm_dict = {}
            while True:
                try:
                    crm_dict[i] = fhandler.getrname(i).replace('chr', '')
                    i += 1
                except ValueError:
                    break
            for r in fhandler:
                if r.is_unmapped:
                    continue
                if r.tags[1][1] != 1:
                    continue
                positive   = not r.is_reverse
                crm        = crm_dict[r.tid]
                len_seq    = len(r.seq)
                pos        = r.pos + (0 if positive else len_seq)
                frag_piece = frags[crm][pos / frag_chunk]
                idx        = bisect(frag_piece, pos)
                prev_re    = frag_piece[idx - 1]
                next_re    = frag_piece[idx]
                name       = r.qname

                frag_count[(crm, prev_re)] += 1
                reads.append('%s\t%s\t%d\t%d\t%d\t%d\t%d\n' % (
                    name, crm, pos, positive, len_seq, prev_re, next_re))
        reads_fh = open('results_1/reads%d.tsv' % (read + 1), 'w')
        reads_fh.write(''.join(sorted(reads)))
        reads_fh.close()
    del(reads)