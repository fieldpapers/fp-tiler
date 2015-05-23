VERSION ?= latest

default:
	docker run --rm \
	  -p 8080:8080 \
	  -v $$(pwd):/app \
	  --env-file .env \
	  fieldpapers/tiler:$(VERSION)

image:
	docker build -t fieldpapers/tiler:$(VERSION) .

publish-image:
	docker push fieldpapers/tiler:$(VERSION)
