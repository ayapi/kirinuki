from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("sqlite_vec")
binaries = collect_dynamic_libs("sqlite_vec")
