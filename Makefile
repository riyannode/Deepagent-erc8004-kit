.PHONY: build doctor status register register-again agent-register clear-expired-locks live-check

build:
	docker compose build

doctor:
	docker compose run --rm erc8004-live doctor

status:
	docker compose run --rm erc8004-live status

register:
	docker compose run --rm erc8004-live register

register-again:
	docker compose run --rm erc8004-live register

agent-register:
	docker compose run --rm erc8004-live agent-register

clear-expired-locks:
	docker compose run --rm erc8004-live clear-expired-locks

live-check: build doctor status register register-again
