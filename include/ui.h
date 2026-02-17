#include "includes.h"



namespace py = pybind11;

class MyWindow : public QWidget {
    Q_OBJECT 

public:
    MyWindow(py::module_& python_logic);

private slots:
    void onButtonClicked(); 

private:
    py::module_& logic;
    QLabel* label;
    QPushButton* button;
};