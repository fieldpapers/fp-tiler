FROM node:22

RUN \
  useradd -d /app -m fieldpapers

USER fieldpapers
ENV HOME /app
WORKDIR /app

ADD . /app/

RUN \
  npm install

VOLUME ["/app"]
EXPOSE 8080

CMD npm start
