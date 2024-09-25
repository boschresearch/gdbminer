## Compile statically and with debug

  clang -g -O0 -o json json.c 
  
## Debug 
  gdb --args ./json seeds/json.input.1