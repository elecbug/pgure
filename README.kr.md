# P-Gure

[English](README.md)

P-Gure는 P2P(Peer-to-Peer) 네트워크의 토폴로지와 그 위에서 동작하는 프로토콜을
그림으로 표현하기 위한 재사용 가능한 Python 라이브러리를 만드는 프로젝트입니다.
논문이나 발표 자료에 넣을 그림을 준비하는 연구자를 위해 설계합니다.

연구자가 Python에서 피어와 링크를 한 번 정의하고 같은 토폴로지를 여러 그림에
활용할 수 있도록 하는 것이 목표입니다. 노드 배치와 시각적 표기 방식을 일관되게
유지하면 독자가 메시지 전달 경로, 피어의 역할, 네트워크 상태를 비교하기 쉽습니다.

피어와 링크, 메시지 경로는 YAML에 적고 색과 선 모양은 같은 폴더의
`gossip.meta.yaml`에 정의합니다. `gossip.yaml`을 불러오면 두 파일이 함께 적용됩니다.

```python
from pgure import load, save_figure

save_figure(load("docs/gossip.yaml"), "gossip.svg")
```

[예제 모음](examples/README.md)에서 트리 브로드캐스트, 토큰 링, 블록 요청과 응답,
두 클러스터 사이의 메시지 전달을 YAML과 그림으로 볼 수 있습니다.

PNG, JPEG, WebP는
`python -m pip install -e '.[raster]'`로 이미지 변환 패키지를 설치한 뒤 파일 확장자를
선택하면 됩니다. [YAML 그림 가이드](docs/figure-yaml.md)

## 로컬 개발

Python 3.10 이상의 가상 환경을 활성화한 뒤 저장소 루트에서 다음 명령을 실행합니다.
편집 가능 모드로 설치하면 `src/pgure/`의 변경 사항이 다음번 패키지를 불러올 때 반영됩니다.

```sh
python -m pip install -e .
python -c "import pgure"
```
