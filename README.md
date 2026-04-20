# E2EE Chat App (NUKS projekt)

Cloud-native end-to-end encrypted chat aplikacija, razvita za predmet NUKS.
Projekt je sestavljen iz več mikrostoritev, ki delujejo prek Docker Compose.

## Namestitev in zagon

### Predpogoji
- Linux z Docker in docker-compose
- `sudo` dostop za izvajanje kontejnerjev

### Hitri zagon
```bash
cd /home/uporabnik/E2EE
chmod +x start.sh stop.sh
./start.sh
```

### Ustavitev
```bash
./stop.sh
```

### Preverjanje delovanja
- API Gateway: `curl http://localhost:8000/health`
- Auth service: `curl http://localhost:8001/health`
- Chat service: `curl http://localhost:8002/health`
- Message service: `curl http://localhost:8003/health`
- Media service: `curl http://localhost:8004/health`

Če je domena nastavljena, lahko dostopate tudi prek:
- `https://secra.top/health`

## Kaj je v projektu

Projekt vsebuje naslednje komponente:

- `auth_service` - registracija, prijava, JWT avtentikacija, upravljanje uporabnikov
- `chat_service` - ustvarjanje in upravljanje chatov ter članov
- `message_service` - shranjevanje in vračanje šifriranih sporočil
- `media_service` - upravljanje medijskih datotek preko MinIO (S3)
- `api_gateway` - FastAPI proxy, ki usmerja zahteve do posameznih storitev
- `nginx` - preprost reverse proxy za zunanje HTTP/HTTPS zahteve
- `postgres` - relacijska baza za avtorizacijo
- `redis` - hitri cache/in-memory store
- `mongodb` - dokumentna baza za sporočila
- `minio` - lokalni S3-compatibilen shranjevalnik

## Struktura projekta

```text
E2EE/
  README.md
  docker-compose.yml
  start.sh
  stop.sh
  services/
    auth_service/
    chat_service/
    message_service/
    media_service/
    api_gateway/
```

## Kako deluje

- Odjemalec (Android app) šifrira sporočila s Signal protokolom.
- Backend prejme in shranjuje samo ciphertext ter metapodatke.
- JWT se uporablja za avtentikacijo in avtorizacijo.
- NGINX/API Gateway poskrbi za enotno vstopno točko za vse storitve.

## Docker Compose

Projekt se zaženete z `docker-compose.yml`, ki vsebuje vse potrebne storitve:
- nginx
- api_gateway
- auth_service
- chat_service
- message_service
- media_service
- postgres
- redis
- mongodb
- minio

## Opombe

- Zunanji dostop naj bo usmerjen prek API Gateway / NGINX.
- Notranjih mikroservisov ni priporočljivo izpostavljati javno brez dodatne zaščite.
- Ta README je osredotočen na zagon in uporabo; nadaljnji razvoj lahko doda metrike, logiranje in CI/CD.
