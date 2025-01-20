5. Thread 55 "tokio-runtime-w" received signal SIGPIPE, Broken pipe. Steps:

     - 5.1
         * sudo apt install rust-gdb
      
      - 5.2.
          * sudo RUST_LOG=trace RUST_BACKTRACE=full rust-gdb --args /config/workspace/ffplayout-dev/target/x86_64-unknown-linux-musl/debug/ffplayout --public=./frontend/.output/public --db="./db" --logs="./log" -l 0.0.0.0:8787
      - 5.3  
           * For help, type "help".
            Type "apropos word" to search for commands related to "word"...
            Reading symbols from /config/workspace/ffplayout-dev/target/x86_64-unknown-linux-musl/debug/ffplayout...
            Python Exception <class 'ModuleNotFoundError'>: No module named 'rust_types'
            (gdb) run
    
      - 5.4  
          * Restarting the channel multiple times quickly using the "Restart Playout" button
       
      - 5.5 
           * [DEBUG] Stop all child processes from channel: 1
            Thread 55 "tokio-runtime-w" received signal SIGPIPE, Broken pipe.
            [Switching to LWP 2410423]        sccp () at ../src_musl/src/thread/__syscall_cp.c:11
            warning: 11     ../src_musl/src/thread/__syscall_cp.c: No such file or directory
      - 5.6 
           * (gdb) bt
      
      - 5.7
           * backtrace: [backtrace1.txt](https://github.com/user-attachments/files/18443817/backtrace1.txt)