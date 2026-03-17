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



private:
    QPushButton *m_btn;
    QLabel *m_status;
    
    QWebSocket *m_socket;
};