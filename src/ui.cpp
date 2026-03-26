#include "ui.h"

#include "includes.h"

MyWindow::MyWindow(QWidget *parent) : QWidget(parent) {
    auto layout = new QVBoxLayout(this);
    m_btn = new QPushButton("Connect");
    m_status = new QLabel("Status: Disconnected");
    f_btn = new QPushButton("Send mp3 file");
    layout->addWidget(m_status);
    layout->addWidget(f_btn);
    layout->addWidget(  m_btn);

    m_socket = new QWebSocket();

    connect(m_socket,&QWebSocket::connected,this,&MyWindow::onConnected);
    connect(m_socket, &QWebSocket::textMessageReceived,this,&MyWindow::onTextMessage);


    connect(f_btn,&QPushButton::clicked,this,&MyWindow::onSendFileClicked);
    connect(m_btn,&QPushButton::clicked, this , &MyWindow::onConnectionClicked);
}



void MyWindow::onConnected(){
    m_status->setText("Connected");
    m_btn->setEnabled(false);
}

void MyWindow::onTextMessage(QString msg) {
    qDebug() << "Server response:" << msg;

    QJsonDocument doc = QJsonDocument::fromJson(msg.toUtf8());
    QJsonObject obj = doc.object();
    
    QString status = obj["status"].toString();
    QString text = obj["text"].toString();

    if (status == "partial") {
        m_status->setText("Распознаю: " + text);
    } 
    else if (status == "final") {
        m_status->setText("ФИНАЛ: " + text);
    }
    else if (status == "processing") {
        m_status->setText("Нейросеть генерирует отчет...");
    }
    else if (status == "protocol") {
        m_status->setText("Отчет готов! Смотри в консоль.");
        qDebug() << "=== ПРОТОКОЛ ===\n" << text;
    }
}



void MyWindow::onConnectionClicked(){
    m_status->setText("Connecting");
    m_socket->open(QUrl("ws://localhost:8765"));
}

void MyWindow::onSendFileClicked() {
    QString filePath = QFileDialog::getOpenFileName(this, "Выберите аудиофайл", "", "Audio Files (*.mp3 *.wav *.ogg)");
    if (filePath.isEmpty()) return;

    qDebug() << "Начинаем декодирование файла:" << filePath;
    m_status->setText("Конвертация MP3...");

    QAudioDecoder *decoder = new QAudioDecoder(this);
    
    QAudioFormat format;
    format.setSampleRate(16000);
    format.setChannelCount(1);
    format.setSampleFormat(QAudioFormat::Int16);
    decoder->setAudioFormat(format);
    decoder->setSource(QUrl::fromLocalFile(filePath));

    QByteArray *decodedData = new QByteArray();

    connect(decoder, &QAudioDecoder::bufferReady, this, [decoder, decodedData]() {
        QAudioBuffer buffer = decoder->read();
         if (buffer.isValid() && buffer.byteCount() > 0) {
            decodedData->append(buffer.constData<char>(), buffer.byteCount());
        }
    });

    connect(decoder, &QAudioDecoder::finished, this, [this, decoder, decodedData]() {
        qDebug() << "Декодирование завершено! Размер сырых данных:" << decodedData->size() << "байт.";
        m_status->setText("Стриминг на сервер...");
        decoder->deleteLater(); 

        QTimer *timer = new QTimer(this);
        int *offset = new int(0); 

        connect(timer, &QTimer::timeout, this,[this, timer, decodedData, offset]() {
            if (*offset < decodedData->size()) {
                  QByteArray chunk = decodedData->mid(*offset, 3200);
                
                if (chunk.size() % 2 != 0) {
                    chunk.chop(1);
                }
                
                m_socket->sendBinaryMessage(chunk);
                *offset += 3200;
            } else {
                timer->stop();
                delete decodedData;
                delete offset;
                timer->deleteLater();

                qDebug() << "Весь файл отправлен. Ждем финальный текст...";
                
                QJsonObject cmd;
                cmd["command"] = "stop_audio";
                m_socket->sendTextMessage(QJsonDocument(cmd).toJson());
            }
        });

        timer->start(100);
    });

    connect(decoder, qOverload<QAudioDecoder::Error>(&QAudioDecoder::error), this, [this, decoder]() {
        qDebug() << "Ошибка декодирования:" << decoder->errorString();
        m_status->setText("❌ Ошибка чтения файла!");
        decoder->deleteLater();
    });

    decoder->start();
}