## Compile statically and with debug

  clang++ -g -O0 -D_GLIBCXX_DEBUG -o jsoncpp json.cpp 
  
## Debug 
  gdb --args ./jsoncpp ../json/seeds/json.input.1