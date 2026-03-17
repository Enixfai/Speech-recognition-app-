
#include "ui.h"

#include "includes.h"

int main(int argc, char *argv[]) {
    QApplication app(argc, argv);
    
    MyWindow window;
    window.setWindowTitle("Test");
    window.resize(400, 300);
    window.show();
    
    return app.exec();
}