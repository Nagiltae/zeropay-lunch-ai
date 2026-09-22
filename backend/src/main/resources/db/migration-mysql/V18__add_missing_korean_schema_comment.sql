-- V17 적용 후 확인된 V9 추가 컬럼의 설명을 보완한다.
ALTER TABLE conversations
    MODIFY COLUMN radius_meters INT NOT NULL DEFAULT 500 COMMENT '대화에서 사용하는 추천 검색 반경(미터).';
