#!/usr/bin/env python3

import codegen

TAG = 'rpcgen'

if __name__ == '__main__':
    args = codegen.create_args(TAG).parse_args()
    print("%s processing %s -> %s" % (TAG, args.input, args.output))

    outputfile = open(args.output, 'w+')

    codegen.HeaderBlock(TAG, args.input).write(outputfile)
