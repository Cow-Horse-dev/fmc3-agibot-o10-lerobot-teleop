#----------------------------------------------------------------
# Generated CMake target import file for configuration "Release".
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "airbot_hardware::airbot_hardware" for configuration "Release"
set_property(TARGET airbot_hardware::airbot_hardware APPEND PROPERTY IMPORTED_CONFIGURATIONS RELEASE)
set_target_properties(airbot_hardware::airbot_hardware PROPERTIES
  IMPORTED_LOCATION_RELEASE "${_IMPORT_PREFIX}/lib/libairbot_hardware.so.0.2.8"
  IMPORTED_SONAME_RELEASE "libairbot_hardware.so.0"
  )

list(APPEND _cmake_import_check_targets airbot_hardware::airbot_hardware )
list(APPEND _cmake_import_check_files_for_airbot_hardware::airbot_hardware "${_IMPORT_PREFIX}/lib/libairbot_hardware.so.0.2.8" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
