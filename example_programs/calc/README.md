## Compile statically and with debug

  clang -g -O0 -o calc calc.c 
  
## Debug 
  gdb --args ./calc seeds/input.1
