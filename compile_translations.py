#!/usr/bin/env python
"""
Compila arquivos de tradução .ts em .qm para o Ghost Downloader 3.
Uso: python compile_translations.py
"""
import subprocess
import pathlib
import sys

def compile_ts_to_qm():
    """Compila todos os .ts em .qm usando lrelease."""
    i18n_dir = pathlib.Path(__file__).parent / "app" / "assets" / "i18n"
    ts_files = sorted(i18n_dir.glob("gd3.*.ts"))
    
    if not ts_files:
        print("❌ Nenhum arquivo .ts encontrado em app/assets/i18n/")
        return False
    
    print(f"📦 Compilando {len(ts_files)} arquivos de tradução...")
    failed = []
    
    for ts_file in ts_files:
        qm_file = ts_file.with_suffix(".qm")
        print(f"\n  ➜ {ts_file.name} → {qm_file.name}")
        
        try:
            result = subprocess.run(
                ["lrelease", str(ts_file), "-qm", str(qm_file)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                if qm_file.exists():
                    size = qm_file.stat().st_size
                    print(f"     ✅ OK ({size} bytes)")
                else:
                    print(f"     ⚠️  Compilado mas arquivo não encontrado")
                    failed.append(ts_file.name)
            else:
                print(f"     ❌ Erro: {result.stderr}")
                failed.append(ts_file.name)
        except FileNotFoundError:
            print(f"     ❌ lrelease não encontrado no PATH")
            failed.append(ts_file.name)
        except subprocess.TimeoutExpired:
            print(f"     ❌ Timeout")
            failed.append(ts_file.name)
    
    print("\n" + "="*60)
    if failed:
        print(f"❌ Compilação completada com {len(failed)} erros:")
        for name in failed:
            print(f"   - {name}")
        return False
    else:
        print(f"✅ Todos os {len(ts_files)} arquivos compilados com sucesso!")
        return True

if __name__ == "__main__":
    success = compile_ts_to_qm()
    sys.exit(0 if success else 1)
