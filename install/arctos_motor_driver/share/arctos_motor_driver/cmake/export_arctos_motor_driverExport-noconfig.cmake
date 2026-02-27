#----------------------------------------------------------------
# Generated CMake target import file.
#----------------------------------------------------------------

# Commands may need to know the format version.
set(CMAKE_IMPORT_FILE_VERSION 1)

# Import target "arctos_motor_driver::can_protocol" for configuration ""
set_property(TARGET arctos_motor_driver::can_protocol APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(arctos_motor_driver::can_protocol PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libcan_protocol.so"
  IMPORTED_SONAME_NOCONFIG "libcan_protocol.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS arctos_motor_driver::can_protocol )
list(APPEND _IMPORT_CHECK_FILES_FOR_arctos_motor_driver::can_protocol "${_IMPORT_PREFIX}/lib/libcan_protocol.so" )

# Import target "arctos_motor_driver::uart_protocol" for configuration ""
set_property(TARGET arctos_motor_driver::uart_protocol APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(arctos_motor_driver::uart_protocol PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libuart_protocol.so"
  IMPORTED_SONAME_NOCONFIG "libuart_protocol.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS arctos_motor_driver::uart_protocol )
list(APPEND _IMPORT_CHECK_FILES_FOR_arctos_motor_driver::uart_protocol "${_IMPORT_PREFIX}/lib/libuart_protocol.so" )

# Import target "arctos_motor_driver::arctos_motor_driver" for configuration ""
set_property(TARGET arctos_motor_driver::arctos_motor_driver APPEND PROPERTY IMPORTED_CONFIGURATIONS NOCONFIG)
set_target_properties(arctos_motor_driver::arctos_motor_driver PROPERTIES
  IMPORTED_LOCATION_NOCONFIG "${_IMPORT_PREFIX}/lib/libarctos_motor_driver.so"
  IMPORTED_SONAME_NOCONFIG "libarctos_motor_driver.so"
  )

list(APPEND _IMPORT_CHECK_TARGETS arctos_motor_driver::arctos_motor_driver )
list(APPEND _IMPORT_CHECK_FILES_FOR_arctos_motor_driver::arctos_motor_driver "${_IMPORT_PREFIX}/lib/libarctos_motor_driver.so" )

# Commands beyond this point should not need to know the version.
set(CMAKE_IMPORT_FILE_VERSION)
