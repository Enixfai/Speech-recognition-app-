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
    void onMicClicked(); 
    void onAudioReady();


private:
    QPushButton *m_btn;
    QPushButton *f_btn;
    QLabel *m_status;
    QWebSocket *m_socket;
     QPushButton *m_micBtn; 
    QAudioSource *m_audioSource; 
    QIODevice *m_audioDevice;    
    bool m_isRecording = false;
};