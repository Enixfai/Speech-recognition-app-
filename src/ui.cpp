#include "ui.h"

MyWindow::MyWindow(py::module_& python_logic) : logic(python_logic) {
    QLayout* layout = new QVBoxLayout(this);

    label = new QLabel("Push", this);
    button = new QPushButton("Call", this);

    layout->addWidget(label);
    layout->addWidget(button);

    connect(button, &QPushButton::clicked, this, &MyWindow::onButtonClicked);
}

void MyWindow::onButtonClicked() {
    try {
        std::string result = logic.attr("get_greeting")().cast<std::string>();
        label->setText(QString::fromStdString(result));
    } catch (py::error_already_set &e) {
        label->setText("Error!");
    }
}