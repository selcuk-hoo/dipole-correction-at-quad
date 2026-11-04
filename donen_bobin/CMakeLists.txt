# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
cmake_minimum_required(VERSION 3.13)

# Set the board architecture to RP2350
set(PICO_BOARD pico2)
set(PICO_PLATFORM rp2350-arm-s)

# Initialize the Pico SDK
include(pico_sdk_import.cmake)

project(MGF C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the SDK
pico_sdk_init()

# ===========================================================================
# Wiznet ioLibrary_Driver (shared by stator)
# ===========================================================================
set(IOLIBRARY_DIR ${CMAKE_CURRENT_LIST_DIR}/lib/ioLibrary_Driver)

# ===========================================================================
# ROTOR TARGET
# ===========================================================================
add_executable(rotor 
    src/rotor.cpp
    lib/ADS1263/ads1263.cpp
)

pico_set_program_name(rotor "mgf_rotor")
pico_set_program_version(rotor "2.0")

# Enable stdio over USB for rotor
pico_enable_stdio_usb(rotor 1)
pico_enable_stdio_uart(rotor 0)

# Include directories
target_include_directories(rotor PRIVATE
    include
    lib/ADS1263
)

# Link standard pico libraries
target_link_libraries(rotor PRIVATE
    pico_stdlib
    hardware_spi
    hardware_dma
    hardware_uart
    hardware_watchdog
)

pico_add_extra_outputs(rotor)

# ===========================================================================
# STATOR TARGET
# ===========================================================================
add_executable(stator 
    src/stator.cpp
    ${IOLIBRARY_DIR}/Ethernet/socket.c
    ${IOLIBRARY_DIR}/Ethernet/wizchip_conf.c
    ${IOLIBRARY_DIR}/Ethernet/W5500/w5500.c
)

pico_set_program_name(stator "mgf_stator")
pico_set_program_version(stator "2.0")

# Enable stdio over USB for stator
pico_enable_stdio_usb(stator 1)
pico_enable_stdio_uart(stator 0)

target_include_directories(stator PRIVATE
    include
    ${IOLIBRARY_DIR}/Ethernet
    ${IOLIBRARY_DIR}/Ethernet/W5500
    lib/quadrature_encoder/src
)

# Define W5500 chip selection for ioLibrary
target_compile_definitions(stator PRIVATE
    _WIZCHIP_=W5500
)

target_link_libraries(stator PRIVATE
    pico_stdlib
    pico_multicore
    hardware_spi
    hardware_dma
    hardware_uart
    hardware_watchdog
    hardware_pio
    hardware_timer
    hardware_clocks
)

# PIO headers generation
pico_generate_pio_header(stator ${CMAKE_CURRENT_LIST_DIR}/lib/ws2812/src/ws2812.pio)
pico_generate_pio_header(stator ${CMAKE_CURRENT_LIST_DIR}/lib/quadrature_encoder/src/quadrature.pio)
pico_generate_pio_header(stator ${CMAKE_CURRENT_LIST_DIR}/src/stepper.pio)

pico_add_extra_outputs(stator)
