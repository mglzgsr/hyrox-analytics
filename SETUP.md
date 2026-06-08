# Setup en servidor Linux

## 1. Clonar el repo

```bash
cd /opt
git clone https://github.com/mglzgsr/hyrox-analytics.git hyrox
cd /opt/hyrox
```

## 2. Crear venv e instalar dependencias

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## 3. Crear directorio de datos

```bash
mkdir -p /opt/hyrox/data
```

## 4. Instalar el servicio systemd

```bash
cp hyrox-dashboard.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable hyrox-dashboard
systemctl start hyrox-dashboard
```

## 5. Instalar el GitHub Actions runner

En GitHub → Settings → Actions → Runners → New self-hosted runner.
Instalar en `/opt/hyrox/actions-runner` y registrar con el token que da GitHub.

```bash
mkdir -p /opt/hyrox/actions-runner
cd /opt/hyrox/actions-runner
# seguir las instrucciones de GitHub para descargar y configurar el runner
./config.sh --url https://github.com/mglzgsr/hyrox-analytics --token TU_TOKEN
./svc.sh install
./svc.sh start
```

## 6. Permitir al runner reiniciar el servicio sin contraseña

```bash
echo "ALL ALL=NOPASSWD: /bin/systemctl restart hyrox-dashboard" >> /etc/sudoers.d/hyrox
```

## 7. Cloudflare Tunnel

Añadir en el tunnel existente:
- Hostname: `hyrox.mglzgsr.com`
- Service: `http://localhost:8003`
