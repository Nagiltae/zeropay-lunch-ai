# KOMSCO-only resolver failure audit (17)

| ID | Provider | Status | Classification | Name | Address | Query | Attempts |
|---:|---|---|---|---|---|---|---:|
| 7549 | I0000015 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 튤립 | 서울특별시 강남구 언주로149길 12 지하층 | 논현동 튤립 | 3 |
  - rank 1: 명품세탁 튤립크리닝세탁소 / road `서울 강남구 논현로146길 43 1층 튤립크리닝` / jibun `서울 강남구 논현동 68-23` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 2: 장미꽃닭발야식 / road `서울 서초구 서운로 138 서초동아타워 지하1층 주방7호` / jibun `서울 서초구 서초동 1321-6 아타워 지하1층 주방7호` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 3: 바이레도 갤러리아 명품관향수 / road `서울 강남구 압구정로 343 갤러리아 명품관 west 1층` / jibun `서울 강남구 압구정동 494` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
| 7553 | I0000015 | AMBIGUOUS | UNCLEAR | 부산집 | 서울특별시 강남구 강남대로150길 10 (논현동) 1층 | 논현동 부산집 | 5 |
  - rank 1: 부산아구찜 / road `서울 서초구 사평대로55길 42` / jibun `서울 서초구 반포동 738` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 2: 부산삼정한정식 / road `서울 강남구 테헤란로7길 8 IBC오피스텔 1층` / jibun `서울 강남구 역삼동 648-1` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 3: 부산아지매국밥 GS타워점국밥 / road `서울 강남구 테헤란로27길 26` / jibun `서울 강남구 역삼동 670-15` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 4: 부산아지매국밥 역삼점 / road `서울 강남구 논현로85길 5-3 청도빌딩 1층` / jibun `서울 강남구 역삼동 738-10` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 5: 부산아구아귀찜,해물찜 / road `서울 강남구 강남대로150길 10` / jibun `서울 강남구 논현동 16-1` / name `DIFFERENT` / address `STRONG_MATCH` / `NAME_MISMATCH`
| 7554 | I0000015 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 제주생선구이 올래밥상 | 서울 강남구 논현로 613, 1층 (논현동) | 제주생선구이올래밥상 | 5 |
  - rank 1: 제주생선구이올래밥상 / road `경기 성남시 분당구 내정로165번길 38 602동 2층 215-1호, 215-2호` / jibun `경기 성남시 분당구 수내동 32` / name `EXACT` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 2: 제주생선구이올래밥상 여의도직영점생선구이 / road `서울 영등포구 여의대방로69길 28 2층 208호, 210호` / jibun `서울 영등포구 여의도동 43-1` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 3: 제주생선구이 올래밥상 사당점 / road `서울 관악구 남현1길 40 지하 1층` / jibun `서울 관악구 남현동 1062-1` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 4: 제주생선구이올래밥상 고삼호수휴게소점생선구이 / road `경기 안성시 고삼면 봉산리 산11-9` / jibun `경기 안성시 고삼면 봉산리 산11-9` / name `CONTAINED` / address `DIFFERENT` / `DETAIL_ADDRESS_PARSE_SUSPECT`
  - rank 5: 올래밥상 제주생선구이생선구이 / road `전북 익산시 선화로1길 109-26 1층 올래밥상 제주생선구이` / jibun `전북 익산시 모현동2가 640` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
| 7557 | I0000015 | AMBIGUOUS | CORRECT_CANDIDATE_PRESENT | 부대찌개매니아 돈돌 | 서울특별시 강남구 선릉로129길 11 논현동242-18 2층  부대찌개매니아돈돌 | 논현동 부대찌개매니아 돈돌 | 1 |
  - rank 1: 돈돌 부대찌개 매니아 강남구청점찌개,전골 / road `서울 강남구 선릉로129길 11 논현동242-18 2층` / jibun `서울 강남구 논현동 242-18 242-18 2층` / name `DIFFERENT` / address `STRONG_MATCH` / `NAME_MISMATCH`
| 7562 | I0000015 | AMBIGUOUS | CORRECT_CANDIDATE_PRESENT | 하나마토 논현점 | 서울 강남구 학동로2길 31, 1층 (논현동) | 논현동 하나마토 논현점 | 1 |
  - rank 1: 하나마토 신논현 / road `서울 강남구 학동로2길 31 1층` / jibun `서울 강남구 논현동 144-3` / name `DIFFERENT` / address `STRONG_MATCH` / `NAME_MISMATCH`
| 7566 | I0000015 | AMBIGUOUS | CORRECT_CANDIDATE_PRESENT | 60년전통 신촌황소곱창(논현점) | 서울 강남구 봉은사로1길 37, 지상 1층 (논현동, 호서빌딩) 60년 전통 신촌 황소곱창 | 논현동 60년전통 신촌황소곱창(논현점) | 3 |
  - rank 1: 60년전통 신촌황소곱창 논현직영점곱창,막창,양 / road `서울 강남구 봉은사로1길 37 지상1층` / jibun `서울 강남구 논현동 165-16` / name `DIFFERENT` / address `STRONG_MATCH` / `NAME_MISMATCH`
  - rank 2: 60년전통신촌황소곱창 강남역직영점 / road `서울 강남구 강남대로100길 13 스타빌딩 지상1층` / jibun `서울 강남구 역삼동 619-5` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
  - rank 3: 60년전통신촌황소곱창 선릉직영점곱창,막창,양 / road `서울 강남구 선릉로86길 32` / jibun `서울 강남구 대치동 896-18` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
| 7568 | I0000015 | NOT_FOUND | UNCLEAR | 완도1957별관 | 서울특별시 강남구 학동로 338 지상1층s109호 | 논현동 완도1957별관 | 0 |
| 7573 | I0000015 | NOT_FOUND | UNCLEAR | 지알(GR)해마루 | 서울특별시 강남구 선릉로 623 2층 해마루 도시락 지알(GR) 해마루 | 논현동 지알(GR)해마루 | 0 |
| 7876 | I0000003 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 호두당 | 서울특별시 강남구 도산대로 지하102 | 호두당 | 5 |
  - rank 1: 호두당 서초역점호두과자 / road `서울 서초구 서초대로 233` / jibun `서울 서초구 서초동 1748-5` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 2: 호두당 용인동백점호두과자 / road `경기 용인시 기흥구 동백중앙로 203 미주타운 107호` / jibun `경기 용인시 기흥구 중동 848-2` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 3: 호두당 서초우면점호두과자 / road `서울 서초구 양재대로2길 100-11 1층 101호` / jibun `서울 서초구 우면동 764` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 4: 호두당 수원세류점호두과자 / road `경기 수원시 권선구 세지로 74 1층 호두당 수원세류점` / jibun `경기 수원시 권선구 권선동 999-4` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 5: 호두당 구로디지털점호두과자 / road `서울 구로구 시흥대로163길 33 주호타워 1층 107호` / jibun `서울 구로구 구로동 1129-1` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
| 8365 | I0000003 | NOT_FOUND | UNCLEAR | 핫브레드 논현역점 | 서울특별시 강남구 학동로 지하102 | 논현동 핫브레드 논현역점 | 0 |
| 7563 | I0000003 | AMBIGUOUS | CORRECT_CANDIDATE_PRESENT | 담소소사골순대국(강남구청역) | 서울특별시 강남구 선릉로131길 25 | 논현동 담소소사골순대국(강남구청역) | 1 |
  - rank 1: 담소소사골순대육개장 강남구청역점순대,순댓국 / road `서울 강남구 선릉로131길 25 1층` / jibun `서울 강남구 논현동 118` / name `DIFFERENT` / address `STRONG_MATCH` / `NAME_MISMATCH`
| 7721 | I0000002 | NOT_FOUND | UNCLEAR | 호두당 신사점 | 서울특별시 강남구 도산대로 지하102(신사동) 327-114호 | 논현동 호두당 신사점 | 0 |
| 7759 | I0000002 | NOT_FOUND | UNCLEAR | 핫브레드 논현역점 | 서울특별시 강남구 학동로 지하102(논현동) 지하2층 731-201호 | 논현동 핫브레드 논현역점 | 0 |
| 7552 | I0000002 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 신천할매떡볶이 | 서울특별시 강남구 봉은사로29길 12 (논현동) 1층 | 논현동 신천할매떡볶이 | 1 |
  - rank 1: 신떡순 신천할매떡볶이 논현점분식 / road `서울 강남구 논현로114길 10 102호` / jibun `서울 강남구 논현동 234-2` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
| 7564 | I0000002 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 족발대감 | 서울특별시 강남구 논현로 613 (논현동) 지하1층 | 논현동 족발대감 | 1 |
  - rank 1: 대감왕족발족발,보쌈 / road `서울 강남구 압구정로 216` / jibun `서울 강남구 신사동 615-1` / name `DIFFERENT` / address `DIFFERENT` / `NAME_AND_ADDRESS_MISMATCH`
| 7565 | I0000002 | AMBIGUOUS | CORRECT_CANDIDATE_NOT_PRESENT | 베이직 | 서울시 강남구 논현로132길 24 1층 101호 | 논현동 베이직 | 5 |
  - rank 1: 베이직바(BAR) / road `서울 강남구 봉은사로 135 2층` / jibun `서울 강남구 논현동 204-4` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 2: 베이직교회개신교 / road `서울 강남구 도산대로24길 29` / jibun `서울 강남구 논현동 32-20` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 3: 닥터베이직의원피부과 / road `서울 강남구 강남대로 478 제우빌딩` / jibun `서울 강남구 논현동 200` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 4: 김형진베이직성형외과의원 / road `서울 강남구 논현로 824 동양빌딩 4층` / jibun `서울 강남구 신사동 591` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
  - rank 5: 베이직연습실장소대여 / road `서울 강남구 테헤란로8길 28-4 주건축물 제지1층 비01호` / jibun `서울 강남구 역삼동 827-50` / name `CONTAINED` / address `DIFFERENT` / `ADDRESS_MISMATCH`
| 7567 | I0000002 | NOT_FOUND | UNCLEAR | 호별관 | 서울특별시 강남구 논현로114길 22 (논현동) 1층 호별관 | 논현동 호별관 | 0 |

## Source fields
- 7549: provider=I0000015, coords=(37.5205560,127.0331175), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=지하층, postal_code=06048, external_merchant_id=264e8f7bef8713eb6ebc587df887f859
- 7553: provider=I0000015, coords=(37.5157780,127.0207026), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=1층, postal_code=06038, external_merchant_id=38fda7760493ae7742fc55bf81d375c3
- 7554: provider=I0000015, coords=(37.5085138,127.0329362), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=613, 1층 (논현동), postal_code=06122, external_merchant_id=7194884b6c5c089f673d1876c85a74ec
- 7557: provider=I0000015, coords=(37.5161343,127.0406515), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=논현동242-18 2층  부대찌개매니아돈돌, postal_code=06099, external_merchant_id=c8e1e2ad2a123919862e38e1e3e17382
- 7562: provider=I0000015, coords=(37.5094294,127.0232986), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=31, 1층 (논현동), postal_code=06114, external_merchant_id=3bcf90de4375576cefd4b513cc78af0e
- 7566: provider=I0000015, coords=(37.5071244,127.0239808), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=60년 전통 신촌 황소곱창, postal_code=06119, external_merchant_id=88fa078070eb1f21bf7114642e8b365b
- 7568: provider=I0000015, coords=(37.5165403,127.0401622), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=NULL, postal_code=06099, external_merchant_id=6ed7c620e46532d1ab37278cd5ee67aa
- 7573: provider=I0000015, coords=(37.5122242,127.0429014), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=지알(GR) 해마루, postal_code=06103, external_merchant_id=f8ac58236a037c0c3efc5b336581e061
- 7876: provider=I0000003, coords=(NULL,NULL), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=NULL, postal_code=06038, external_merchant_id=cedc122a66e870a606bdd95243119f8c
- 8365: provider=I0000003, coords=(NULL,NULL), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=NULL, postal_code=06110, external_merchant_id=14b481fc258c21dc6b41660f78cef102
- 7563: provider=I0000003, coords=(37.5171765,127.0389163), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=NULL, postal_code=06060, external_merchant_id=42702eda39b78916f7bdca0a04b0471a
- 7721: provider=I0000002, coords=(NULL,NULL), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=327-114호, postal_code=06038, external_merchant_id=c8171f72d52e8df2543d7ff7165965fc
- 7759: provider=I0000002, coords=(NULL,NULL), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=지하2층 731-201호, postal_code=06110, external_merchant_id=bea2bde91c804f96a699c37d71404a28
- 7552: provider=I0000002, coords=(37.5085698,127.0346514), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=1층, postal_code=06109, external_merchant_id=fc24789f0295224efe78ad37ed327a16
- 7564: provider=I0000002, coords=(37.5085182,127.0329590), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=지하1층, postal_code=06122, external_merchant_id=2e59dacc94c145729fb77d06fd90d71b
- 7565: provider=I0000002, coords=(37.5151720,127.0323808), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=1층 101호, postal_code=06052, external_merchant_id=d30fa8ef687251b85b809d8c64dceebd
- 7567: provider=I0000002, coords=(37.5088957,127.0352877), category=NULL, representative_menu=NULL, average_price=NULL, detail_address=1층 호별관, postal_code=06109, external_merchant_id=3db76167ac3862f937c84a6a23de3cc1
