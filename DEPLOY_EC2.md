# AI Hunter EC2 Deployment

## Server

- Ubuntu EC2
- Docker + Docker Compose
- Nginx reverse proxy

## Start

```bash
cd /opt/ai-hunter
docker compose up -d --build
```

## Check

```bash
docker compose ps
curl http://127.0.0.1:8000/api/v1/health
curl -I http://127.0.0.1:3000
```

## Public URL

Open port 80 in the EC2 security group, then visit:

```text
http://<EC2_PUBLIC_IP>
```

## Security Group

Open inbound:

- TCP 80 from `0.0.0.0/0`
- TCP 443 from `0.0.0.0/0` after HTTPS is configured
- TCP 22 only from admin IP

Do not expose backend port 8000 publicly.
