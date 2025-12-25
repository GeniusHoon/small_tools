#Requires AutoHotkey v2.0

; Shift + Space를 눌렀을 때 실행
+Space::
{
    ; 한/영 키의 스캔코드(SC1F2)를 직접 전송
    Send "{vk15sc1F2}"
}