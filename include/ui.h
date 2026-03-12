#pragma once
#include <QWidget>
#include <QPushButton>
#include <QLabel>
#include <QtWebSockets/QWebSocket>

class MyWindow : public QWidget {
    Q_OBJECT

public:
    MyWindow(QWidget *parent = nullptr);

private slots:
    void onButtonClicked();
    void onMessageReceived(const QString &message);

private:
    QPushButton *button;
    QLabel *label;
    QWebSocket *webSocket;
};