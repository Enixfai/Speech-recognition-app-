#include <QApplication>
#include "ui.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    
    MyWindow window;
    window.setWindowTitle("Минимальный тест");
    window.resize(400, 300);
    window.show();
    
    return app.exec();
}