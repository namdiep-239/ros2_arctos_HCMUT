#----------------------------------------------------------------
# Generated CMake target import file.
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "arctos_hardware_interface::arctos_interface" for configuration ""
set_property(TARGET arctos_hardware_interface::arctos_interface APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(arctos_hardware_interface::arctos_interface PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libarctos_interface.so"
  IMPORTED_SONAME_NOCONFIG "libarctos_interface.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS arctos_hardware_interface::arctos_interface )
list(APPEND _IMPORT_CHECK_FILES_FOR_arctos_hardware_interface::arctos_interface "${_IMPORT_PREFIX}/lib/libarctos_interface.so" )

# Import target "arctos_hardware_interface::arctos_services" for configuration ""
set_property(TARGET arctos_hardware_interface::arctos_services APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(arctos_hardware_interface::arctos_services PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libarctos_services.so"
  IMPORTED_SONAME_NOCONFIG "libarctos_services.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS arctos_hardware_interface::arctos_services )
list(APPEND _IMPORT_CHECK_FILES_FOR_arctos_hardware_interface::arctos_services "${_IMPORT_PREFIX}/lib/libarctos_services.so" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
