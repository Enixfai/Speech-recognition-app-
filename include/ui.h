#pragma once


#include "includes.h"

class MyWindow : public QWidget {
    Q_OBJECT

public:
    MyWindow(QWidget *parent = nullptr);

private slots:
    void onConnectionClicked();
    void onConnected();
    void onTextMessage(QString msg);
    void onSendFileClicked();


private:
    QPushButton *m_btn;
    QPushButton *f_btn;
    QLabel *m_status;
    QWebSocket *m_socket;
};