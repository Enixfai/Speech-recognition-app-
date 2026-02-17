cmake_minimum_required(VERSION 3.20)
project(MyProject VERSION 1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF) 
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)


set(CMAKE_AUTOMOC ON) 
set(CMAKE_AUTOUIC ON) 
set(CMAKE_AUTORCC ON)

find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 CONFIG REQUIRED)
find_package(Qt6 COMPONENTS Widgets REQUIRED)

add_executable(myapp
src/main.cpp
src/ui.cpp
include/ui.h 
)

target_include_directories(myapp PRIVATE ${CMAKE_SOURCE_DIR}/include)

target_link_libraries(myapp PRIVATE 
pybind11::embed
Qt::Widgets
)


if(EXISTS "${CMAKE_SOURCE_DIR}/scripts")
    file(COPY ${CMAKE_SOURCE_DIR}/scripts/ DESTINATION ${CMAKE_BINARY_DIR})
endif()