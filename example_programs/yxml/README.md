## Compile statically and with debug

  clang -g -O0 -o yxml yxml.c 
  
## Debug 
  gdb --args ./yxml seeds/yxml.input.1