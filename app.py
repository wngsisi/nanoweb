import asyncio
import json
import os
import cv2
from aiohttp import web
from av import VideoFrame
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
import fractions
import time
pcs = set()
relay = None

class CameraVideoStreamTrack(MediaStreamTrack):

    kind = "video"

    def __init__(self):
        super().__init__()
        self._timestamp = 0
        try:

            self.cap = cv2.VideoCapture('rtsp://admin:123456@192.168.1.102:554/h264/ch1/sub/av_stream')
            if not self.cap.isOpened():
                raise Exception("Cannot open RTSP")

            if not self.cap.isOpened():
                raise Exception("Cannot open camera")

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

            ret, frame = self.cap.read()

            if not ret or frame is None:
                raise Exception("cannot read camera frame")

            print("Camera initialized successfully")
        except Exception as e:
            print(f"Camera initialization failed: {str(e)}")
            raise

    async def next_timestamp(self):
        if self._timestamp == 0:
            self._timestamp = int(time.time() * 1000000000)
        else:
            self._timestamp += int(1000000000 / 30)  # 30fps
        return self._timestamp, fractions.Fraction(1, 30)

    async def recv(self):
        try:
            ret, frame = self.cap.read()

            if not ret or frame is None:
                print("Cannot read camera frame")
                return None

            if frame.size == 0:
                print("Empty frame")
                return None
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, c = frame.shape
            cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 0, 255), 3)
            cv2.line(frame, (0, h // 2), (w, h // 2), (255, 0, 255), 3)
            pts, time_base = await self.next_timestamp()
            new_frame = VideoFrame.from_ndarray(frame, format="rgb24")
            new_frame.pts = pts
            new_frame.time_base = time_base

            return new_frame
        except Exception as e:
            print(f"Error processing video frame: {str(e)}")
            return None

    def stop(self):
        if hasattr(self, 'cap') and self.cap is not None:
            self.cap.release()

async def index(request):
    content = open(os.path.join(os.path.dirname(__file__), "templates/index.html"), "r", encoding='utf-8').read()
    return web.Response(content_type="text/html", text=content)

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        print(f"Connection state is {pc.connectionState}")
        if pc.connectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    video = CameraVideoStreamTrack()
    pc.addTrack(video)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type
        })
    )

async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

if __name__ == "__main__":
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer)
    #app.router.add_static('/static', 'static')

    port = 8080
    print(f"Starting WebRTC server at http://localhost:{port}")
    web.run_app(app, host='0.0.0.0', port=port)
