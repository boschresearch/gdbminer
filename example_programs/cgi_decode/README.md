## Compile statically and with debug

  clang -g -O0 -o cgi_decode cgi_decode.c 
  
## Debug 
  gdb --args ./json seeds/cgi_decode.input.1