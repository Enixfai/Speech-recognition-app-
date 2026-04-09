#include "includes.h"
#include "ui.h"
MyWindow::MyWindow(QWidget *parent) : QWidget(parent) {
    this->resize(650, 500);
    this->setWindowTitle("AI Meeting Assistant");

    auto *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(25, 25, 25, 25); 
    mainLayout->setSpacing(15); 

    m_status = new QLabel("Ожидание подключения...", this);
    m_status->setAlignment(Qt::AlignCenter); 

    m_logWindow = new QTextEdit(this);
    m_logWindow->setReadOnly(true); 
    m_logWindow->setPlaceholderText("Здесь будет появляться текст распознавания и итоговый протокол...");

    auto *btnLayout = new QHBoxLayout();
    btnLayout->setSpacing(15);

    m_btn = new QPushButton("Подключиться", this);
    m_micBtn = new QPushButton("Микрофон", this);
    f_btn = new QPushButton("Загрузить MP3", this);

    btnLayout->addWidget(m_btn);
    btnLayout->addWidget(m_micBtn);
    btnLayout->addWidget(f_btn);

    mainLayout->addWidget(m_status);
    mainLayout->addWidget(m_logWindow, 1); 
    mainLayout->addLayout(btnLayout);

    QString styleSheet = R"(
        QWidget {
            background-color: #1e1e2e;
            color: #cdd6f4;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
        }
        QLabel {
            font-size: 16px;
            font-weight: bold;
            color: #a6e3a1; /* Светло-зеленый */
        }
        QTextEdit {
            background-color: #181825;
            border: 2px solid #313244;
            border-radius: 10px;
            padding: 10px;
            color: #cdd6f4;
            font-size: 15px;
        }
        QPushButton {
            background-color: #89b4fa; /* Приятный синий */
            color: #11111b;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #b4befe; /* Цвет при наведении */
        }
        QPushButton:disabled {
            background-color: #45475a;
            color: #6c7086;
        }
    )";
    this->setStyleSheet(styleSheet); 

    m_socket = new QWebSocket();
    connect(m_micBtn, &QPushButton::clicked, this, &MyWindow::onMicClicked);

    QAudioFormat format;
    format.setSampleRate(16000);
    format.setChannelCount(1);
    format.setSampleFormat(QAudioFormat::Int16);

    m_audioSource = new QAudioSource(format, this);

    connect(m_socket, &QWebSocket::connected, this, &MyWindow::onConnected);
    connect(m_socket, &QWebSocket::textMessageReceived, this, &MyWindow::onTextMessage);
    connect(f_btn, &QPushButton::clicked, this, &MyWindow::onSendFileClicked);
    connect(m_btn, &QPushButton::clicked, this, &MyWindow::onConnectionClicked);
}

void MyWindow::onMicClicked() {
    if (!m_socket->isValid()) {
        m_status->setText("❌ Сначала нажмите Connect!");
        return;
    }

    if (!m_isRecording) {
        m_isRecording = true;
        m_micBtn->setText("🛑 Стоп микрофона");
        m_status->setText("Слушаю... Говорите!");

        m_audioDevice = m_audioSource->start();
        
        m_audioDevice->disconnect(); 
        connect(m_audioDevice, &QIODevice::readyRead, this, &MyWindow::onAudioReady);
        
    } else {
        m_isRecording = false;
        m_micBtn->setText("🎙 Старт микрофона");
        m_status->setText("Запись остановлена. Ждем финал...");
        m_audioSource->stop(); 

        QJsonObject cmd;
        cmd["command"] = "stop_audio";
        m_socket->sendTextMessage(QJsonDocument(cmd).toJson());

        QJsonObject reportCmd;
        reportCmd["command"] = "generate_protocol";
        reportCmd["text"] = m_fullText; 
        m_socket->sendTextMessage(QJsonDocument(reportCmd).toJson());
    }
}

void MyWindow::onAudioReady() {
    if (!m_audioDevice) return;

    QByteArray data = m_audioDevice->readAll();

    if (data.size() % 2 != 0) {
        data.chop(1);
    }

    if (data.size() > 0 && m_socket->isValid()) {
        m_socket->sendBinaryMessage(data);
    }
}

void MyWindow::onConnected() {
    m_status->setText("Connected");
    m_btn->setEnabled(false);
}
void MyWindow::onTextMessage(QString msg) {
    QJsonDocument doc = QJsonDocument::fromJson(msg.toUtf8());
    QJsonObject obj = doc.object();
    
    QString status = obj["status"].toString();
    QString text = obj["text"].toString();

    if (status == "partial") {
        m_status->setText("🎙 Распознаю...");
        
        m_logWindow->setHtml(m_fullText + "<font color='#a6adc8'><i>" + text + "</i></font>");
    } 
    else if (status == "final") {
        m_status->setText("✅ Фраза записана");
        
        if (!text.trimmed().isEmpty()) {
            m_fullText += "<b>Вы:</b> " + text + "<br><br>";
        }
        
        m_logWindow->setHtml(m_fullText);
    }
    else if (status == "processing") {
        m_status->setText("⏳ Нейросеть генерирует Markdown отчет...");
        m_logWindow->setHtml(m_fullText + "<br><i>Анализирую текст совещания...</i>");
    }
    else if (status == "protocol") {
        m_status->setText("✅ Отчет готов!");
        m_fullText = ""; 
        m_logWindow->setMarkdown(text); 
    }
}

void MyWindow::onConnectionClicked() {
    m_status->setText("Connecting...");
    m_socket->open(QUrl("ws://localhost:8765"));
}

void MyWindow::onSendFileClicked() {
    if (!m_socket->isValid()) {
        m_status->setText("❌ Сначала нажмите Connect!");
        return;
    }

    QString filePath = QFileDialog::getOpenFileName(this, "Выберите аудиофайл", "", "Audio Files (*.mp3 *.wav *.ogg)");
    if (filePath.isEmpty()) return;

    m_status->setText("Конвертация MP3...");
    QAudioDecoder *decoder = new QAudioDecoder(this);
    
    QAudioFormat format;
    format.setSampleRate(16000);
    format.setChannelCount(1);
    format.setSampleFormat(QAudioFormat::Int16);
    decoder->setAudioFormat(format);
    decoder->setSource(QUrl::fromLocalFile(filePath));

    auto decodedData = std::make_shared<QByteArray>();

    connect(decoder, &QAudioDecoder::bufferReady, this,[decoder, decodedData]() {
        QAudioBuffer buffer = decoder->read();
        if (buffer.isValid() && buffer.byteCount() > 0) {
            decodedData->append(buffer.constData<char>(), buffer.byteCount());
        }
    });

    connect(decoder, &QAudioDecoder::finished, this, [this, decoder, decodedData]() {
        m_status->setText("Стриминг на сервер...");

        QTimer *timer = new QTimer(this);

        connect(timer, &QTimer::timeout, this, [this, timer, decodedData, offset = 0]() mutable {
            if (offset < decodedData->size()) {
                QByteArray chunk = decodedData->mid(offset, 32000);
                
                if (chunk.size() % 2 != 0) chunk.chop(1);

                m_socket->sendBinaryMessage(chunk);
                offset += 32000;
            } else {
                timer->stop();
                timer->deleteLater();

                QJsonObject cmd;
                cmd["command"] = "stop_audio";
                m_socket->sendTextMessage(QJsonDocument(cmd).toJson());
            }
        });

        timer->start(100);
    });

    connect(decoder, qOverload<QAudioDecoder::Error>(&QAudioDecoder::error), this,[this, decoder]() {
        m_status->setText("❌ Ошибка чтения файла!");
    });

    decoder->start();
}