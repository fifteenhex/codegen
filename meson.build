project('codegen', 'c')

headers = '--headers=' + meson.current_source_dir() + '/include/'

prog_sqlitegen = find_program('sqlitegen.py')
gen_sqlitegen = generator(prog_sqlitegen,
                 output : ['@BASENAME@.sqlite.h'],
                 arguments : ['--input=@INPUT@', '--output=@BUILD_DIR@/@BASENAME@.sqlite.h', headers])
                 
prog_jsongen = find_program('jsongen.py')
gen_jsongen = generator(prog_jsongen,
                 output : ['@BASENAME@.json.h'],
                 arguments : ['--input=@INPUT@', '--output=@BUILD_DIR@/@BASENAME@.json.h', headers])
                 
prog_rpcgen = find_program('rpcgen.py')
gen_rpcgen = generator(prog_rpcgen,
                 output : ['@BASENAME@.rpc.h'],
                 arguments : ['--input=@INPUT@', '--output=@BUILD_DIR@/@BASENAME@.rpc.h', headers])
                 
inc = include_directories('include')
dep = declare_dependency(include_directories : inc)