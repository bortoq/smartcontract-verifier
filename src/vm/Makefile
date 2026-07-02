# Makefile for the VM runtime (C implementation of the single-instruction VM)
# Build with:  make
# Test with:   make test

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2 -I.
DEPS = space.h invariants.h
OBJ = space.o bitcpy.o invariants.o

.PHONY: all clean test

all: libvm.a

libvm.a: $(OBJ)
	ar rcs $@ $^

space.o: space.c $(DEPS)
	$(CC) $(CFLAGS) -c -o $@ $<

bitcpy.o: bitcpy.c $(DEPS)
	$(CC) $(CFLAGS) -c -o $@ $<

invariants.o: invariants.c $(DEPS)
	$(CC) $(CFLAGS) -c -o $@ $<

# Build a test program that runs a simple VM tick
test_vm: test_vm.c libvm.a
	$(CC) $(CFLAGS) -o $@ $^

test: test_vm
	./test_vm

clean:
	rm -f *.o *.a test_vm
