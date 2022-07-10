# --------------------------------------------------------------------------------------------------
# Builder Image
# --------------------------------------------------------------------------------------------------
FROM alpine:3.16 as builder

# Package required tools for all flavour's "builder" stage
RUN set -eux \
	&& apk add --update --no-cache \
		bc \
		cargo \
		cmake \
		curl \
		g++ \
		gcc \
		git \
		libffi-dev \
		libxml2-dev \
		libxslt-dev \
		make \
		musl-dev \
		openssl-dev \
		py3-pip \
		python3 \
		python3-dev \
		rust


# Pip required modules for "builder" stage
RUN set -eux \
	&& pip3 install --no-cache-dir --no-compile wheel \
	&& pip3 install --no-cache-dir --no-compile -r requirements.txt \
	&& find /usr/lib/ -name '__pycache__' -print0 | xargs -0 -n1 rm -rf \
	&& find /usr/lib/ -name '*.pyc' -print0 | xargs -0 -n1 rm -rf

# Clean-up some site-packages to save space
RUN set -eux \
	&& pip3 uninstall --yes \
	setuptools \
	wheel

# --------------------------------------------------------------------------------------------------
# Final Image
# --------------------------------------------------------------------------------------------------
FROM alpine:3.16 as production

RUN set -eux \
	&& apk add --no-cache \
		python3 \
	&& ln -sf /usr/bin/python3 /usr/bin/python \
	&& rm -rf /tmp/* \
	&& rm -rf /var/tmp/* \
	&& find /usr/lib/ -name '__pycache__' -print0 | xargs -0 -n1 rm -rf \
	&& find /usr/lib/ -name '*.pyc' -print0 | xargs -0 -n1 rm -rf

COPY --from=builder /usr/lib/python3.10/site-packages/ /usr/lib/python3.10/site-packages/

WORKDIR /src
ADD pikube-unifi.py /src

CMD ["kopf", "run", "/src/pikube-unify.py", "--verbose"]