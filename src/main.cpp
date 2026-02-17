#include "includes.h"
#include "ui.h"

namespace py = pybind11;

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);

    py::scoped_interpreter guard{};
    py::module_::import("sys").attr("path").attr("append")(".");

    try {
        py::module_ logic = py::module_::import("test");

        MyWindow window(logic);
        window.resize(300, 200);
        window.show();

        return app.exec();

    } catch (py::error_already_set &e) {
        return 1;
    }
}