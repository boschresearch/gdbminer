# GDBMiner: Debugger-driven-Grammar-Mining


This is the companion code for the the paper GDBMiner: Mining Precise Input Grammars on (almost) any System  by Eisele et al.  The code allows the users to
reproduce and extend the results reported in the study. Please cite the
above paper when reporting, reproducing or extending the results.

## Purpose of the project

This software is a research prototype, solely developed for and published as
part of the publication cited above. It will neither be
maintained nor monitored in any way.

## Install local 
    sudo apt install graphviz graphviz-dev gdb
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .

## Config File
GDBMiner uses config files for passing required options.


    [BASIC]
    # Path to a directory containing seed files
    seed_directory = <path>
    # Path to a directory where output files (e.g. graphs, logfiles) are stored.
    output_directory = <path>

    # Path to the binary target file
    binary_file = <path>

    # Path to directory containing eval files
    eval_directory = <path>

    # This section contains configurations which are relevant for GDB
    [GDB]
    gdb_path = /usr/bin/gdb
    instance = valgrind

    # tracing will ignore function names that match the following regex 
    # see https://docs.python.org/3/library/re.html
    ignore_functions_regex = @plt|_vgr

    # Type of watchpoint (e.g. (uint8_t*), (uint16_t*), (uint32_t*), (char*), etc.).
    # Sometimes it can be a little bit tricky to find the correct type because
    # (uint8_t*) == (char*) == (uint8*) but it is not everytime clear, which type will be accepted.
    # You know you do it wrong if you get the ERROR message 'No symbol table is loaded.  Use the "file" command.' when
    # setting a watchpoint
    watchpoint_type = (char*)
    # Number of available watchpoints 
    watchpoint_count = 10000

    # Time how long GDB should wait for responses from GDBServer in seconds
    timeout = 30

    # Address or symbol name where tracing should start
    entrypoint = <symbol_name|address>

    # Address or symbol name where tracing should end
    # or empty if tracing should stop when stepping out of entry function
    exitpoint = <symbol_name|address|empty>

    #The address of the input buffer or symbol name
    input_buffer = <symbol_name|address>
   
    [LOGS]
    # One of {DEBUG, INFO, WARNING, ERROR, CRITICAL}
    log_level = INFO


## Generate inputs from a golden grammar
To evaluate GDBMiner, we generate inputs using a grammar. For instance, create 1000 inputs for evaluation:

    ./src/eval/generate_inputs.py --config ./example_programs/json/configuration/configuration.ini --grammar ./example_programs/json/json.grammar ./example_programs/json/eval 1000   

## Run local
GDBMiner requires two steps tracing the processing of the seed inputs and the subsequential mining step. Execute with:

    ./src/tracer/trace.py --config ./example_programs/json/configuration/configuration.ini
    ./src/miner/mine.py --config ./example_programs/json/configuration/configuration.ini

The following files will be stored to the configured output folder:
    
    *.trace - A trace file for every input
    parsing_g.json - The mined grammar
    
To generate inputs from a mined grammar, use:
    
    from fuzzingbook.GrammarMiner import readable
    from fuzzingbook.Grammars import START_SYMBOL
    from fuzzingbook.GrammarFuzzer import GrammarFuzzer
    import json
    import pathlib

    WORKING_DIRECTORY = pathlib.Path("./output/json/trial-0/")

    with open(WORKING_DIRECTORY / "parsing_g.json", 'r') as f: 
       grammar_file = json.load(f)
       grammar = grammar_file["[grammar]"]
       grammar[START_SYMBOL] = [["<START>"]]

       f = GrammarFuzzer(readable(grammar))

       for i in range(10):
          print(f.fuzz())

## Calculate precision and recall
Calculate precision and recall values using the eval inputs and the mined grammar

    ./src/eval/precision_recall.py --config ./example_programs/json/configuration/configuration.ini

## Run evaluation experiment in docker 
Running a full evaluation can take multiple days. If you want to limit the number of evaluation targets, modify the `run_experiments.py` script.

    docker build . -t gdbminer
    docker run --rm  -v $( pwd)/output:/output/ gdbminer /run_experiment.sh

## Run multiple trials

    # Start 50 trials
    NO_TRIALS=50; for i in  $(seq 1 $NO_TRIALS); do docker run -d --rm  -v $( pwd)/output_$i:/output/ --name gdbminer_$i gdbminer /run_experiment.sh; done

    # Average results and  calculate std deviation with Welfords algorithm
    for miner in arvada treevada gdbminer mimid
    do
        printf "\n$miner precision recall f1-score\n"
        for target in cgi_decode json mjs tinyc calc yxml  calcrs jsonrs calccpp  jsoncpp  xmlcpp
        do
            cat output_*/$target.*$miner.result | jq  .precision,.recall |xargs -n2 echo | awk -v target="$target" '{x1=$1;b1=a1+(x1-a1)/NR;q1+=(x1-a1)*(x1-b1);a1=b1; x2=$2;b2=a2+(x2-a2)/NR;q2+=(x2-a2)*(x2-b2);a2=b2} END {std1 = sqrt(q1/NR); std2 = sqrt(q2/NR); printf("%-10s: %0.2f:%0.2f 		| %0.2f:%0.2f 		| %0.2f\n", target, a1 * 100, std1 * 100, a2* 100, std2 * 100,  200 * (a1 * a2) / (a1+a2))  } '
        done
    done

## Execute on new binary

GDBMiner relies on a valid stack layout at every point in execution, which is why the target binary programs need to be build without optimizations. Also debug symbols are required to name non terminals in the resulting grammar.
Unfortunately on C++ binaries the compiler generated symbol names are required. This leads tu ugly entrypoint names like `_ZN8picojson5parseIPKcEET_RNS_5valueERKS3_S7_PNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE`instead of just `picojson::parse<const_char_*>`


## GDBMiner on STM32  B-L4S5I-IOT01A board

In this case the B-L4S5I-IOT01A and its on-board debugger are used. This on-board debugger sets up a GDB server via the 'st-util' program, and enables access to this GDB server via localhost:4242.


- Install the STLINK driver [link](https://www.st.com/content/st_com/en/products/development-tools/software-development-tools/stm32-software-development-tools/stm32-utilities/stsw-link009.html)
- Connect MCU board and PC via USB (on MCU board, connect to the USB connector that is labeled as 'USB STLINK')


~~~
sudo apt-get install stlink-tools gdb-multiarch libusb-dev
~~~


Build and flash a firmware for the STM32 B-L4S5I-IOT01A, for example the arduinojson project.

Prerequisite: Install [platformio (pio)](https://docs.platformio.org/en/latest//core/installation.html#super-quick-mac-linux)
~~~
cd ./example_firmware/stm32_arduinojson/
pio run --target upload
~~~

If a `LIBUSB_ERROR_ACCESS` occurs, put 

    # STLink v2
    ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="664", GROUP="plugdev"

into `/etc/udev/rules.d/90-stm32.rules`and run `sudo udevadm control --reload` to reload. Ensure that your user belongs to the `plugdev`group.


For your info: platformio stored an .elf file of the SUT here: ./example_firmware/stm32_arduinojson/.pio/build/disco_l4s5i_iot01a/firmware.elf 

Check the config at `./example_firmware/stm32_arduinojson/configuration/configuration.ini` and start tracing and mining:

    ./src/tracer/trace.py --config ./example_firmware/stm32_arduinojson/configuration/configuration.ini
    
    ./src/miner/mine.py --config ./example_firmware/stm32_arduinojson/configuration/configuration.ini


## SVGPP

Install dependencies

sudo apt-get install libboost-all-dev cmake inkscape liblzma-dev

Download LibXML2 https://github.com/GNOME/libxml2 and compile statically with debug:


    git clone https://github.com/GNOME/libxml2.git
    cd libxml2
    git checkout v2.12.4 
    mkdir build
    cd build
    cmake -D LIBXML2_WITH_ZLIB=OFF -D LIBXML2_WITH_LZMA=OFF  -DLIBXML2_WITH_ICONV=OFF -DLIBXML2_WITH_THREADS=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="-O0" ..
    make 
    sudo make install
    sudo ldconfig

Tested in commit f460b2c7ceba92a875c0ba5c333826652863b396 from https://github.com/svgpp/svgpp.git
Compile SVGPP with the static LibXML2 library and debug:

    cd example_programs/svgcpp/svgpp/src/demo/render/
    mkdir build
    cd build 
    cmake -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-O0 -DDEBUG" ..
    make

Translate SVGs into PDFs

    inkscape --export-type=pdf --export-area-drawing --export-overwrite <file>.svg
    

Run in Docker Container

    docker run --rm  -v $( pwd)/output:/output/ gdbminer python3 /GDBMiner/src/tracer/trace.py --config /example_programs/svgcpp/configuration_libxml.ini

    docker run --rm  -v $( pwd)/output:/output/ gdbminer python3 /GDBMiner/src/miner/mine.py --config /example_programs/svgcpp/configuration_libxml.ini


## License

GDBMiner is open-sourced under the AGPL-3.0 license. See the
[LICENSE](LICENSE) file for details.

For a list of other open source components included in PROJECT-NAME, see the
file [3rd-party-licenses.txt](3rd-party-licenses.txt).
