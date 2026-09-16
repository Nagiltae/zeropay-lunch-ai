# 실행 및 배포

## 로컬 개발

처음 환경을 준비할 때는 저장소 루트의 `./scripts/setup.sh`를 실행합니다. 스크립트는 필수 도구를 검사하고 잠금 파일 기반 의존성을 준비한 뒤 MySQL과 Qdrant를 기동하여 health 상태를 확인합니다.

애플리케이션 코드를 각 런타임에서 직접 실행하고 데이터 저장소만 Docker Compose로 실행할 수도 있습니다.

```bash
docker compose up -d mysql qdrant
```

- React: Vite 개발 서버
- Spring Boot: Gradle `bootRun`
- FastAPI: Poetry와 Uvicorn
- MySQL과 Qdrant: Docker Compose

Spring Boot 설정은 다음 프로필로 분리합니다.

| 프로필 | 용도 | 연결 방식 |
| --- | --- | --- |
| `local` | 애플리케이션을 개발 PC에서 직접 실행 | `localhost`의 MySQL과 FastAPI |
| `dev` | 개발 PC의 Docker Compose 전체 스택 | Compose 호스트명 `mysql`, `ai` |
| `prod` | AWS 운영 환경 | 모든 연결 정보와 자격 증명을 환경변수로 주입 |

YAML에는 DB 비밀번호나 운영 자격 증명을 저장하지 않습니다. `local` 실행도 `.env`를 Spring Boot가 자동으로 읽지 않으므로 필요한 값을 환경변수로 전달해야 합니다.

```bash
cd backend
SPRING_PROFILES_ACTIVE=local \
MYSQL_USER=zeropay \
MYSQL_PASSWORD=zeropay_local \
./gradlew bootRun
```

위 값은 로컬 예시이며 운영 값으로 사용하지 않습니다. `local`과 `dev`는 샘플 음식점 migration을 실행하고 `prod`는 공통 스키마 migration만 실행합니다.

MySQL과 Qdrant 포트는 로컬 호스트에만 바인딩됩니다. 컨테이너가 없어도 Compose가 이미지를 내려받고 컨테이너와 영속 볼륨을 생성합니다.

## 로컬 통합 테스트

전체 서비스를 컨테이너로 실행합니다.

```bash
docker compose up --build -d
docker compose ps
```

React 정적 파일은 Nginx가 제공합니다. Nginx는 `/api/` 요청을 Spring Boot로 전달하며 FastAPI를 직접 노출하지 않습니다. Spring Boot는 Compose 내부 호스트명 `ai`와 `mysql`을 사용하고, FastAPI는 `qdrant`를 사용합니다.

Compose는 Spring Boot에 `SPRING_PROFILES_ACTIVE=dev`를 설정합니다.

채팅 API의 SSE 이벤트가 브라우저에 즉시 전달되도록 Nginx의 `/api/` 프록시는 응답 버퍼링과 캐시를 사용하지 않으며 읽기 제한 시간을 300초로 설정합니다.

```text
브라우저
  -> Nginx + React
      -> Spring Boot
          -> MySQL
          -> FastAPI
              -> Qdrant
```

컨테이너는 `docker compose down`으로 중지합니다. 이 명령은 `mysql-data`와 `qdrant-data` 볼륨을 삭제하지 않습니다.

## AWS EC2 배포 방향

운영 배포에서는 로컬에서 사용한 Dockerfile로 이미지를 빌드해 Amazon ECR에 저장하고, EC2가 이미지를 내려받아 Docker Compose로 실행합니다.

- 외부에는 Nginx의 HTTP/HTTPS 포트만 공개
- Spring Boot와 FastAPI는 Compose 내부 네트워크에서 실행
- 운영 MySQL은 Amazon RDS 사용 권장
- Qdrant는 초기에는 EC2의 영속 볼륨에서 실행 가능
- 비밀 정보는 저장소의 `.env`가 아니라 AWS Systems Manager Parameter Store 또는 Secrets Manager로 관리
- 이미지 태그는 `latest` 대신 Git 커밋 SHA 사용

EC2용 Compose 파일과 CI/CD 워크플로는 AWS 계정, ECR 저장소, 도메인, RDS 연결 정보가 정해진 뒤 추가합니다.
