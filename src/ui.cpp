#include "ui.h"
#include <QVBoxLayout>#include "ui.h"
#include <QVBoxLayout>

MyWindow::MyWindow(QWidget *parent) : QWidget(parent) {
    auto *layout = new QVBoxLayout(this);
    label = new QLabel("Ждем ответа...", this);
    button = new QPushButton("Отправить 'Привет' в Питон", this);

    layout->addWidget(label);
    layout->addWidget(button);

    // 1. Создаем сокет
    webSocket = new QWebSocket();
    
    // 2. Указываем, что делать, когда Питон пришлет ответ
    connect(webSocket, &QWebSocket::textMessageReceived, this, &MyWindow::onMessageReceived);

    // 3. Подключаемся к Питону (адрес должен совпадать с server.py)
    webSocket->open(QUrl("ws://localhost:8765"));

    // 4. Настраиваем кнопку
    connect(button, &QPushButton::clicked, this, &MyWindow::onButtonClicked);
}

void MyWindow::onButtonClicked() {
    // Проверяем, есть ли связь
    if (webSocket->isValid()) {
        webSocket->sendTextMessage("Привет от C++!");
        label->setText("Отправлено. Ждем...");
    } else {
        label->setText("Ошибка: Нет связи с сервером!");
    }
}

void MyWindow::onMessageReceived(const QString &message) {
    // Когда Питон ответил, показываем это на экране
    label->setText("Ответ Питона: " + message);
}