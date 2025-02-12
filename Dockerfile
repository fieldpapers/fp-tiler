FROM node:22

USER node

WORKDIR /app
ADD . /app/

RUN npm install

VOLUME ["/app"]
EXPOSE 8080

CMD npm start
