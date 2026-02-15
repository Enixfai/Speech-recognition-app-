#include "includes.h"

namespace py = pybind11;

int main() {
    py::scoped_interpreter guard{};

    try {
        py::module_ sys = py::module_::import("sys");
        sys.attr("path").attr("append")("."); 

        py::module_ logic = py::module_::import("test");
        
        std::string py_msg = logic.attr("get_greeting")().cast<std::string>();

        print_from_cpp(py_msg);

        int sum_res = logic.attr("count_sum")(2,6).cast<int>();

        print_from_cpp(std::to_string(sum_res));
    } catch (py::error_already_set &e) {
        std::cout << "Error: " << e.what() << std::endl;
    }
    return 0;
}