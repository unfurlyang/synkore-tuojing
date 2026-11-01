set(APP_PATH ${CMAKE_CURRENT_LIST_DIR})
aux_source_directory(${APP_PATH}/src APP_SRC)
add_library(${EXAMPLE_LIB})
target_sources(${EXAMPLE_LIB} PRIVATE ${APP_SRC}
    $ENV{OPEN_SDK_ROOT}/src/ai_components/ai_ui/font/font_puhui_16_4.c)
target_include_directories(${EXAMPLE_LIB} PRIVATE ${APP_PATH}/include)
target_compile_options(${EXAMPLE_LIB} PRIVATE -Wall -DLV_LVGL_H_INCLUDE_SIMPLE)
