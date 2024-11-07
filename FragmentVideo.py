import cv2
import time
import base64

video = cv2.VideoCapture("Videos/VideoA.mp4")
fps = video.get(cv2.CAP_PROP_FPS)

# S = F / fps, Segundos = 1 frame / 29.97 fps
frame_interval = 1 / fps

while True:
    try:
        start_time = time.time()
        ret, frame = video.read() # o ret diz se o frame foi bem lido, um boool basicamente

        if not ret:
            break

        _, buffer = cv2.imencode(".jpg", frame)
        encoded_64 = base64.b64encode(buffer)
        # send(encoded_64)

        ######
        # Zona para dar send do buffer. 
        # o que acontece é que nos exemplos que vi eles dao encode base64 depois de dar o imencode do cv2. não me perguntes porquê.
        ######
        # Desta forma, ao receber os frames no cliente também é preciso dar decode de base64 e depois o imdecode do cv2
        ######
        # ganda mistela
        ######

        # ajusta o tempo porque desde o começo do try ate agora perde se tempo e ficava em camera lenta
        end_time = time.time() - start_time
        delay = frame_interval - end_time
        time.sleep(max(0,delay))

    except KeyboardInterrupt:
        video.release()
        cv2.destroyAllWindows()
        break        
