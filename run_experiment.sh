#! /bin/bash

# This script is intended to run in the accompanying docker container!
# It sequentially starts experiments for Cmimid, GDBMiner, and Arvada
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

#Adapt number of seeds to generate in the mimid Makefile
sed -i 's+./build/ 100+./build/ ${NUMBER_OF_SEEDS}+g' /mimid/Cmimid/Makefile

#Change input generation to GrammarCoverageFuzzer
sed -i 's+import fuzzingbook.Parser as P+from fuzzingbook.GrammarCoverageFuzzer import GrammarCoverageFuzzer\nfrom fuzzingbook.GrammarMiner import readable\nfrom eval.generate_inputs import trim_grammar+g' /mimid/Cmimid/src/generateinputs.py
sed -i 's+fuzzer = F.LimitFuzzer(grammar)+fuzzer = GrammarCoverageFuzzer(trim_grammar(readable(grammar), start_symbol=start), start_symbol=start)+g' /mimid/Cmimid/src/generateinputs.py
sed -i 's+v = fuzzer.fuzz(start)+v = fuzzer.fuzz()+g' /mimid/Cmimid/src/generateinputs.py


sed -i 's+import fuzzingbook.Parser as P++g' /mimid/Cmimid/src/fuzz.py
sed -i '14i sys.setrecursionlimit(99000)' /mimid/Cmimid/src/grammar-miner.py

cp /example_programs/calc/calc.c /mimid/Cmimid/examples/
cp /example_programs/calc/calc.grammar /mimid/Cmimid/examples/

cp /example_programs/yxml/yxml.c /mimid/Cmimid/examples/
cp /example_programs/yxml/yxml.h /mimid/Cmimid/examples/
cp /example_programs/yxml/yxml.grammar /mimid/Cmimid/examples/

# Calc and yxml do not work in mimid, but let it still generate seed inputs for us
#make -C /mimid/Cmimid/  build/yxml.out build/yxml.inputs.done.generate


# Run CMimid on all targets (where it works :/)

for target in calc cgi_decode json mjs tiny
do
    START_TIME=$(date +%s)
    make -C /mimid/Cmimid/ build/$target.pgrammar
    END_TIME=$(date +%s)
    # Calculate the execution duration in seconds
    EXECUTION_DURATION=$((END_TIME - START_TIME))
    echo $EXECUTION_DURATION > /output/$target.${NUMBER_OF_SEEDS}.mimid.execution_duration
done

# Rename the tiny seeds to be consistent
rename.ul tiny tinyc /mimid/Cmimid/build/tiny*
mv /output/tiny.20.mimid.execution_duration /output/tinyc.20.mimid.execution_duration

#Copy Mimid grammars to output folder
cp /mimid/Cmimid/build/*-parsing.json /output/

export PYTHONPATH=/GDBMiner/src

for target in calc calcrs calccpp cgi_decode json jsonrs jsoncpp yxml xmlcpp mjs tinyc 
do

    mkdir /example_programs/$target/mimid_seeds
    mkdir /example_programs/$target/mimid_eval
    
    if test -f "/mimid/Cmimid/build/$target.input.1"; then

        #Copy Seeds from the Mimid run if exists
        cp /mimid/Cmimid/build/$target.input.[0-9]* /example_programs/$target/mimid_seeds

        
    else #For others we generate seeds with our script
        python3 /GDBMiner/src/eval/generate_inputs.py --config /example_programs/$target/configuration/configuration_docker.ini --grammar /example_programs/$target/$target.grammar /example_programs/$target/mimid_seeds ${NUMBER_OF_SEEDS}
    fi

    mkdir -p /output/$target/ && cp -rf /example_programs/$target/mimid_seeds /output/$target/seeds 

    # Generate eval inputs from golden grammar
    python3 /GDBMiner/src/eval/generate_inputs.py --config /example_programs/$target/configuration/configuration_docker.ini --grammar /example_programs/$target/$target.grammar /example_programs/$target/mimid_eval ${PRECISION_SET_SIZE}

    START_TIME=$(date +%s)
    # Run GDBMiner
    python3 /GDBMiner/src/tracer/trace.py --config /example_programs/$target/configuration/configuration_docker.ini
    python3 /GDBMiner/src/miner/mine.py --config /example_programs/$target/configuration/configuration_docker.ini
    END_TIME=$(date +%s)
    # Calculate the execution duration in seconds
    EXECUTION_DURATION=$((END_TIME - START_TIME))

    # Calculate Precision recall for GDBMiner
    python3 /GDBMiner/src/eval/precision_recall.py --config /example_programs/$target/configuration/configuration_docker.ini --out /output/$target.${NUMBER_OF_SEEDS}.gdbminer.result

    jq --arg duration "$EXECUTION_DURATION" '.execution_duration = ($duration | tonumber)' /output/$target.${NUMBER_OF_SEEDS}.gdbminer.result > tmp.$$.json && mv tmp.$$.json /output/$target.${NUMBER_OF_SEEDS}.gdbminer.result


    # Calculate Precision recall for CMimid
    python3 /GDBMiner/src/eval/precision_recall.py --config /example_programs/$target/configuration/configuration_docker.ini --grammar /mimid/Cmimid/build/$target-parsing.json --out /output/$target.${NUMBER_OF_SEEDS}.mimid.result
    EXECUTION_DURATION=$(cat /output/$target.${NUMBER_OF_SEEDS}.mimid.execution_duration)
    jq --arg duration "$EXECUTION_DURATION" '.execution_duration = ($duration | tonumber)' /output/$target.${NUMBER_OF_SEEDS}.mimid.result > tmp.$$.json && mv tmp.$$.json /output/$target.${NUMBER_OF_SEEDS}.mimid.result

    #Run Arvada
    START_TIME=$(date +%s)
    python3 /arvada/search.py external /example_programs/$target/$target /example_programs/$target/mimid_seeds/ /output/$target.${NUMBER_OF_SEEDS}.arvada.log
    END_TIME=$(date +%s)
    # Calculate the execution duration in seconds
    EXECUTION_DURATION=$((END_TIME - START_TIME))
    # Calculate precision recall for arvada
    python3 /arvada/eval.py external -n ${PRECISION_SET_SIZE} /example_programs/$target/$target /example_programs/$target/mimid_eval/ /output/$target.${NUMBER_OF_SEEDS}.arvada.log > /tmp/$target.${NUMBER_OF_SEEDS}.arvada.result
    #Convert result to a json format
    tail -n 1 /tmp/$target.${NUMBER_OF_SEEDS}.arvada.result | sed 's+Precision+"precision"+g' |  sed 's+Recall+"recall"+g' | xargs -0 printf "{%s}" > /output/$target.${NUMBER_OF_SEEDS}.arvada.result
    jq --arg duration "$EXECUTION_DURATION" '.execution_duration = ($duration | tonumber)' /output/$target.${NUMBER_OF_SEEDS}.arvada.result > tmp.$$.json && mv tmp.$$.json /output/$target.${NUMBER_OF_SEEDS}.arvada.result

    #Run Treevada
    START_TIME=$(date +%s)
    python3 /treevada/search.py external /example_programs/$target/$target /example_programs/$target/mimid_seeds/ /output/$target.${NUMBER_OF_SEEDS}.treevada.log
    END_TIME=$(date +%s)
    # Calculate the execution duration in seconds
    EXECUTION_DURATION=$((END_TIME - START_TIME))
    # Calculate precision recall for treevada
    python3 /treevada/eval.py external -n ${PRECISION_SET_SIZE} /example_programs/$target/$target /example_programs/$target/mimid_eval/ /output/$target.${NUMBER_OF_SEEDS}.treevada.log > /tmp/$target.${NUMBER_OF_SEEDS}.treevada.result
    #Convert result to a json format
    tail -n 1 /tmp/$target.${NUMBER_OF_SEEDS}.treevada.result | sed 's+Precision+"precision"+g' |  sed 's+Recall+"recall"+g' | xargs -0 printf "{%s}" > /output/$target.${NUMBER_OF_SEEDS}.treevada.result
    jq --arg duration "$EXECUTION_DURATION" '.execution_duration = ($duration | tonumber)' /output/$target.${NUMBER_OF_SEEDS}.treevada.result > tmp.$$.json && mv tmp.$$.json /output/$target.${NUMBER_OF_SEEDS}.treevada.result

done


#Since the docker container runs under root. give rw access for everyone :)
chmod -R a+rw /output
