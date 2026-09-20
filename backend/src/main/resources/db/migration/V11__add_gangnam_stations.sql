-- Update existing 8 stations with verified lines and data source
UPDATE subway_stations 
SET line = '2호선/신분당선', 
    source = 'SEOUL_OPEN_DATA', 
    source_updated_at = CURRENT_TIMESTAMP 
WHERE id = 'gangnam';

UPDATE subway_stations 
SET source = 'SEOUL_OPEN_DATA', 
    source_updated_at = CURRENT_TIMESTAMP 
WHERE id IN ('yeoksam', 'seolleung', 'samseong', 'sinsa', 'apgujeong', 'cheongdam');

UPDATE subway_stations 
SET line = '3호선/수인분당선/SRT', 
    source = 'SEOUL_OPEN_DATA', 
    source_updated_at = CURRENT_TIMESTAMP 
WHERE id = 'suseo';

-- Insert remaining 19 Gangnam-gu stations
INSERT INTO subway_stations (id, name, line, latitude, longitude, active, source, source_updated_at) VALUES
('maebong', '매봉역', '3호선', 37.4869, 127.0467, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('dogok', '도곡역', '3호선/수인분당선', 37.4909, 127.0528, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('daechi', '대치역', '3호선', 37.4946, 127.0631, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('hangnyeoul', '학여울역', '3호선', 37.4967, 127.0706, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('daecheong', '대청역', '3호선', 37.4935, 127.0795, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('irwon', '일원역', '3호선', 37.4839, 127.0762, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('nonhyeon', '논현역', '7호선/신분당선', 37.5110, 127.0214, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('hakdong', '학동역', '7호선', 37.5142, 127.0319, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('gangnamgu_office', '강남구청역', '7호선/수인분당선', 37.5172, 127.0413, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('sinnonhyeon', '신논현역', '9호선/신분당선', 37.5046, 127.0250, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('eonju', '언주역', '9호선', 37.5073, 127.0339, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('seonjeongneung', '선정릉역', '9호선/수인분당선', 37.5103, 127.0436, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('samseong_jungang', '삼성중앙역', '9호선', 37.5130, 127.0531, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('bongeunsa', '봉은사역', '9호선', 37.5142, 127.0602, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('apgujeong_rodeo', '압구정로데오역', '수인분당선', 37.5273, 127.0405, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('hanti', '한티역', '수인분당선', 37.4962, 127.0529, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('guryong', '구룡역', '수인분당선', 37.4868, 127.0589, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('gaepo_dong', '개포동역', '수인분당선', 37.4891, 127.0661, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP),
('daemosan', '대모산입구역', '수인분당선', 37.4914, 127.0727, TRUE, 'SEOUL_OPEN_DATA', CURRENT_TIMESTAMP);
