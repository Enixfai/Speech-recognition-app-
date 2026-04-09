import torch
import platform

print(f"ОС: {platform.system()} {platform.release()}")
print(f"Версия PyTorch: {torch.__version__}")

if torch.cuda.is_available():
    print("✅ CUDA доступна!")
    print(f"Имя GPU: {torch.cuda.get_device_name(0)}")
    print(f"Количество GPU: {torch.cuda.device_count()}")
    print(f"Текущая версия CUDA в Torch: {torch.version.cuda}")
    
    # Тестовый тензор
    x = torch.rand(5, 3).to("cuda")
    print("✅ Тестовый тензор успешно перемещен на GPU")
else:
    print("❌ CUDA НЕ доступна. Всё работает на CPU.")
    if not torch.cuda.is_available():
        print("\nВозможные причины:")
        print("1. У тебя нет видеокарты NVIDIA.")
        print("2. Не установлен драйвер NVIDIA.")
        print("3. Ты установил версию PyTorch без поддержки CUDA (CPU-only).")