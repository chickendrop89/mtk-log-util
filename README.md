# mtk-log-util
My personal mtkclient wrapper for getting bootloader or kernel logs from a mediatek device

## Usage
```shell
mtk-log-util - mtkclient wrapper for getting bootloader or kernel logs from a mediatek device

positional arguments:
  {expdb,pstore}        Choose extraction method: expdb (partition) or pstore (memory)
  filename              Output file to save ASCII strings

options:
  -h, --help            show this help message and exit
  --mtkclient-args MTKCLIENT_ARGS
                        Extra mtkclient arguments (default: "")
  --pstore-address PSTORE_ADDRESS
                        Pstore memory address (default: 0x48090000)
  --pstore-size PSTORE_SIZE
                        Pstore memory size (default: 0xe0000)
  --auto-detect-pstore  Auto-detect pstore address and size from expdb partition (pstore command only)
```

## Basic Examples
Extracting PStore memory region. Will work only if DRAM was not cleared (eg. after panic)
```shell
python logutil.py pstore
```

Extracting preloader/tee/lk logs. Will work only if the partition exists
```shell
python logutil.py expdb
```
