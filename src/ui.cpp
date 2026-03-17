#include "ui.h"

#include "includes.h"

MyWindow::MyWindow(QWidget *parent) : QWidget(parent) {
    auto layout = new QVBoxLayout(this);
    m_btn = new QPushButton("Connect");
    m_status = new QLabel("Status: Disconnected");

    layout->addWidget(m_status);
    layout->addWidget(  m_btn);

    m_socket = new QWebSocket();

    connect(m_socket,&QWebSocket::connected,this,&MyWindow::onConnected);
    connect(m_socket, &QWebSocket::textMessageReceived,this,&MyWindow::onTextMessage);

    connect(m_btn,&QPushButton::clicked, this , &MyWindow::onConnectionClicked);
}



void MyWindow::onConnected(){
    m_status->setText("Connected");
    m_btn->setEnabled(false);
}

void MyWindow::onTextMessage(QString msg){
    qDebug() << "Server response:" <<msg;
}


void MyWindow::onConnectionClicked(){
    m_status->setText("Connecting");
    m_socket->open(QUrl("ws://localhost:8765"));
}
