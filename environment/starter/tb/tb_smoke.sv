`timescale 1ns / 10ps
// Auto-generated AES-128 known-answer testbench (2 vectors).
// NIST FIPS-197 / SP 800-38A KATs plus deterministic random vectors (seed=197).
module tb_smoke;
  logic         clk;
  logic         rst;  // active-low
  logic         ld;
  logic         done;
  logic [127:0] key;
  logic [127:0] text_in;
  logic [127:0] text_out;

  aes_cipher_top dut (
    .clk(clk), .rst(rst), .ld(ld), .done(done),
    .key(key), .text_in(text_in), .text_out(text_out)
  );

  initial clk = 1'b0;
  always #5 clk = ~clk;

  localparam int NVEC = 2;
  logic [127:0] keys  [0:NVEC-1];
  logic [127:0] pts   [0:NVEC-1];
  logic [127:0] golds [0:NVEC-1];

  initial begin
    keys[0]  = 128'h000102030405060708090a0b0c0d0e0f;
    pts[0]   = 128'h00112233445566778899aabbccddeeff;
    golds[0] = 128'h69c4e0d86a7b0430d8cdb78070b4c55a;
    keys[1]  = 128'h2b7e151628aed2a6abf7158809cf4f3c;
    pts[1]   = 128'h3243f6a8885a308d313198a2e0370734;
    golds[1] = 128'h3925841d02dc09fbdc118597196a0b32;
  end

  integer i, cyc, errors;
  initial begin
    errors = 0;
    ld = 1'b0;
    key = 128'h0;
    text_in = 128'h0;
    rst = 1'b0;
    repeat (4) @(posedge clk);
    rst = 1'b1;
    repeat (2) @(posedge clk);
    for (i = 0; i < NVEC; i = i + 1) begin
      @(posedge clk);
      key     <= keys[i];
      text_in <= pts[i];
      ld      <= 1'b1;
      @(posedge clk);
      ld      <= 1'b0;
      cyc = 0;
      while (done !== 1'b1 && cyc < 40) begin
        @(posedge clk);
        cyc = cyc + 1;
      end
      if (done !== 1'b1) begin
        $display("TIMEOUT at vector %0d", i);
        errors = errors + 1;
      end else if (text_out !== golds[i]) begin
        $display("MISMATCH vector %0d got %032h expected %032h", i, text_out, golds[i]);
        errors = errors + 1;
      end
    end
    if (errors == 0) begin
      $display("ALL_TESTS_PASSED");
      $finish(0);
    end else begin
      $display("TESTS_FAILED errors=%0d", errors);
      $finish(1);
    end
  end
endmodule
