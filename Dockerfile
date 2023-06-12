FROM node:20.3

RUN \
  useradd -d /app -m fieldpapers

USER fieldpapers
ENV HOME /app
WORKDIR /app

ADD package.json /app/

RUN \
  npm install

ADD . /app/

VOLUME ["/app"]
EXPOSE 8080

CMD npm start
