
####### Expanded from @PACKAGE_INIT@ by configure_package_config_file() #######
####### Any changes to this file will be overwritten by the next CMake run ####
####### The input file was airbot_hardware-config.cmake.in                            ########

get_filename_component(PACKAGE_PREFIX_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../" ABSOLUTE)

macro(set_and_check _var _file)
  set(${_var} "${_file}")
  if(NOT EXISTS "${_file}")
    message(FATAL_ERROR "File or directory ${_file} referenced by variable ${_var} does not exist !")
  endif()
endmacro()

macro(check_required_components _NAME)
  foreach(comp ${${_NAME}_FIND_COMPONENTS})
    if(NOT ${_NAME}_${comp}_FOUND)
      if(${_NAME}_FIND_REQUIRED_${comp})
        set(${_NAME}_FOUND FALSE)
      endif()
    endif()
  endforeach()
endmacro()

####################################################################################

include(CMakeFindDependencyMacro)

set(AIRBOT_HARDWARE_INSTALL_DEV ON)
set(AIRBOT_HARDWARE_BUILD_STATIC OFF)
set(AIRBOT_HARDWARE_BUILD_EXAMPLES OFF)

# Find dependencies first so they're available when targets file is included
# Only find dependencies if static library target would be exported
if(AIRBOT_HARDWARE_INSTALL_DEV AND AIRBOT_HARDWARE_BUILD_STATIC)
    # Find boost_asio - this is how Boost components are installed in this build
    find_dependency(boost_asio REQUIRED)

    # Find zlog_cpp - the static target should be available after this
    find_dependency(zlog_cpp REQUIRED)

    # Find slamtec
    find_dependency(slamtec REQUIRED)

    find_dependency(concurrentqueue REQUIRED)

    find_dependency(fmt CONFIG REQUIRED)
    if (AIRBOT_HARDWARE_BUILD_EXAMPLES)
        find_dependency(argparse CONFIG REQUIRED)
        find_dependency(Boost CONFIG REQUIRED json)
    endif()
endif()

# Include the targets file - dependencies should now be available
include("${CMAKE_CURRENT_LIST_DIR}/airbot_hardware-targets.cmake")

set(PACKAGE_VERSION "")
