#!/usr/bin/env python2
from fskdemod import FskDemod
import argparse
import numpy as np
import omni_rf as omni
import sys

def show_packet(samples, offsets, streaming_offset, samples_per_bit, sample_rate):
    packet_samples = samples[slice(*offsets)]
    bytes = omni.decode_packet(
        packet_samples,
        samples_per_bit,
        manchester_variant='ieee',
        preamble_byte=0xab)
    hex_str = "".join([format(n, '02x') for n in bytes])
    #print "hex = %s" % hex_str
    computed_crc = omni.compute_crc(str(bytearray(bytes[:-1])))
    if len(hex_str) > 0 and computed_crc == bytes[-1:]:
        sample_num = streaming_offset + offsets[0]
        print "%sms: %s" % (int((sample_num/float(sample_rate))*1000), hex_str)

def main(options=None):

    parser = argparse.ArgumentParser(description='Decode omnipod packets from fsk iq wav file.')
    parser.add_argument('filename', metavar='filename', type=str, nargs='+',
                        help='filename of iq file')

    sample_rate = 2048000      # sample rate of sdr
    samples_per_bit = 50.41    # This was computed based on previously seen data.

    args = parser.parse_args()
    filename = args.filename[0]
    if filename == "-":
        print "Reading demodulated signal from stdin"
        bits_per_chunk = 2048
        bytes_per_sample = 4
        samples_per_chunk = int(bits_per_chunk * samples_per_bit)
        bytes_per_chunk = samples_per_chunk * bytes_per_sample

        samples = np.array([], dtype=np.float32)
        streaming_offset = 0

        header = sys.stdin.read(115)
        if header[:18] == 'Using Volk machine':
            print "Skipping extraneous gnuradio header."
        else:
            # This is valid data; keep it.
            header += sys.stdin.read(1) # byte align to size of float32
            samples = np.frombuffer(header, dtype=np.float32)

        try:
            while True:
                new_bytes = sys.stdin.read(bytes_per_chunk)
                if len(new_bytes) == 0:
                    break
                #print "Read %d bytes" % len(new_bytes)
                mod = len(new_bytes) % 4
                if mod != 0:
                    new_bytes = new_bytes[:-mod]
                samples = np.append(samples, np.frombuffer(new_bytes, dtype=np.float32))
                packets_offsets = omni.find_offsets(samples,samples_per_bit, 80, 1)
                if len(packets_offsets) == 0:
                    # Keep the last chunk
                    streaming_offset += len(samples) - samples_per_chunk
                    samples = samples[-samples_per_chunk:]
                    continue
                else:
                    #print "streaming_offset = %s" % streaming_offset
                    #print "offsets = %s" % packets_offsets
                    end_of_last_processed_packet = 0
                    for packet_offset in packets_offsets:
                        packet_begin = packet_offset[0]
                        packet_end = packet_offset[1]
                        num_bits = (packet_end - packet_begin) / samples_per_bit
                        # If we have enough bits for a packet and some silence after the packet, then process packet
                        #print "num bits = %s" % num_bits
                        if num_bits > 20 and packet_end < (len(samples) - (samples_per_bit*5)):
                            #print "processing"
                            show_packet(samples, packet_offset, streaming_offset, samples_per_bit, sample_rate)
                            end_of_last_processed_packet = packet_end
                    streaming_offset += end_of_last_processed_packet
                    samples = samples[end_of_last_processed_packet:]
        except KeyboardInterrupt:
            pass
    else:
        print "Reading demodulated signal data from %s" % filename
        demod = FskDemod(args.filename[0], '.demod.dat')
        demod.run()

        samples = np.fromfile('.demod.dat',dtype=np.float32)
        packets_offsets = omni.find_offsets(samples,samples_per_bit)

        for po in packets_offsets:
            show_packet(samples, po, streaming_offset, samples_per_bit, sample_rate)

if __name__ == '__main__':
    main()
